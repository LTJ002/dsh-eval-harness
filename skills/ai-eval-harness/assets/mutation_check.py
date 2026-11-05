#!/usr/bin/env python3
"""变异测试（mutation test）：故意把实现改坏，验证 selftest 会不会翻红。

为什么需要它
------------
selftest 全绿**不证明任何东西**——它可能根本没覆盖到关键语义。
本 skill 的教训就是这么来的：一次改动后 53 条断言全过，但把
offline 容忍度从 0 改成 5（等于让离线评测放过真实退化），断言依然全绿。
那种情况下"全绿"是假绿，比红更危险。

做法
----
对源码的**临时副本**施加一处已知缺陷（mutation），跑 selftest（跑的是副本目录里的
selftest，它按 `__file__` 导入同目录被变异的模块——所以变异真的影响被测行为）：
  - 断言翻红  → 测试有区分力，这个语义真被覆盖着
  - 仍然全绿  → **测试是空转的**，必须补断言

源文件全程只读；副本目录跑完即删。早期版本直接改写源文件再 finally 恢复，
进程被杀在写入与恢复之间会留下坏源码——隔离是主保护，恢复只是副本内兜底。

每个变异都先断言"替换确实生效"，否则 mutate 失败也会"全绿"，得到假阳性结论。
（这一点踩过：PowerShell 里用相对路径 + .NET WriteAllText 写文件，
 实际按 .NET 进程 cwd 解析，文件根本没被改，却以为改了。）

用法
----
    python mutation_check.py            # 跑全部变异
    python mutation_check.py --list     # 只列变异点
退出码：0 = 所有变异都被检出；1 = 有变异未被检出（测试有洞）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import os  # 子进程 env 要继承当前环境

HERE = Path(__file__).parent

# Windows 下 stdout 被重定向（CI 捕获、`> 文件`、tee）时按本地码页 GBK 编码，
# 打印中文或替换符会 UnicodeEncodeError 崩掉 —— 门禁在 CI 里必崩、只在交互终端能用。
# 本轮实测：`python mutation_check.py > run.txt` 直接崩，退出码 1。
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


SUBPROC_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

# (名字, 目标文件, 原文, 改成, 期望被哪类断言检出)
MUTATIONS = [
    (
        "离线容忍度放宽",
        "eval_baseline.py",
        'DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 0, "live": 1}',
        'DEFAULT_ALLOW_FLIP = {"offline": 5, "live-strict": 0, "live": 1}',
        "offline 掉 1 条判退化",
    ),
    (
        "在线容忍度取消",
        "eval_baseline.py",
        'DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 0, "live": 1}',
        'DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 0, "live": 0}',
        "live 掉 1 条不判退化（随机性）",
    ),
    (
        "live-strict 退回容忍 1 条",
        "eval_baseline.py",
        'DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 0, "live": 1}',
        'DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 1, "live": 1}',
        "live-strict 掉 1 条判退化（零容忍）",
    ),
    (
        "分母变化不再拦截",
        "eval_baseline.py",
        "        elif base[\"total\"] != t:",
        "        elif False:",
        "分母变化→不判定（退出 2，不是 0 也不是 1）",
    ),
    (
        "小样本不再标注",
        "eval_baseline.py",
        "    if t < MIN_CONCLUSIVE:",
        "    if False:",
        "n<5 标注不足以支撑结论",
    ),
    (
        "失败明细退回子串匹配",
        "eval_baseline.py",
        'detail = [(n, current[n]["failures"]) for n in sorted(failed_names)',
        'detail = [(n, current[n]["failures"]) for n in sorted(current)',
        "明细不误挂同前缀的未退化套件",
    ),
    # 锚点用 _is_consolidated 的函数体，而不是某处调用条件：
    # 调用点有两处（目录模式 + 快照告警），函数体只有一处——
    # 上一轮把调用条件改成 _is_consolidated(name) 后，原本盯着
    # `name == CONSOLIDATED_NAME` 的锚点就失效了（脚本报 ?? 而非 caught）。
    (
        "陈旧快照识别整个失效",
        "eval_baseline.py",
        "    return name == CONSOLIDATED_NAME or name.endswith(\"-results.json\")",
        "    return False",
        "目录模式忽略陈旧汇总",
    ),
    (
        "合并文件后缀规则丢失",
        "eval_baseline.py",
        "or name.endswith(\"-results.json\")",
        "",
        "offline-results.json 不被当分片读入",
    ),
    (
        "基线裸映射不再兼容",
        "eval_baseline.py",
        "            if isinstance(v, dict):",
        "            if False:",
        "裸映射基线可读",
    ),
    (
        "基线 [passed,total] 形状丢失",
        "eval_baseline.py",
        "elif isinstance(v, (list, tuple)) and len(v) == 2:",
        "elif False:",
        "列表形状基线可读",
    ),
    (
        "观测不到又返回空列表",
        "eval_online.py",
        "        return None\n    calls = []\n    seen_conversation = False",
        "        return []\n    calls = []\n    seen_conversation = False",
        "未配置审计源 → None（不是空列表）",
    ),
    (
        "会话不在日志时也返回空列表",
        "eval_online.py",
        "    if not seen_conversation:",
        "    if False:",
        "会话不在日志里 → None（不可判失败）",
    ),
    (
        "PII 退回宽禁词式匹配",
        "eval_online.py",
        "UNMASKED_PHONE = re.compile(r\"(?<!\\d)1[3-9]\\d{9}(?!\\d)\")",
        "UNMASKED_PHONE = re.compile(r\"1[3-9]\\d{9}\")",
        "PII `金额 1380000 元`",
    ),
    # 退出码三态。抽成 exit_code_for 纯函数后，这些变异才可能被抓到——
    # 之前内联在 main() 里，改坏 `total_tested == 0` 时 selftest 仍全绿（实测发生过）。
    (
        "全降级也报通过",
        "eval_online.py",
        "    if tested == 0:\n        return 2",
        "    if tested == 0:\n        return 0",
        "0/0 绝不返回 0",
    ),
    (
        "鉴权余额异常仍报通过",
        "eval_online.py",
        "    if passed < tested:\n        return 1\n    if errors:\n        return 2",
        "    if passed < tested:\n        return 1\n    if False:\n        return 2",
        "无失败但有 402/401 异常 → 2（不可用）",
    ),
    (
        "观测缺口不再拦截",
        "eval_online.py",
        "    if unobserved:\n        return 2",
        "    if unobserved:\n        return 0",
        "部分测到但有用例观测不到 → 2",
    ),
    (
        "真实失败被当成通过",
        "eval_online.py",
        "    if passed < tested:\n        return 1",
        "    if passed < tested:\n        return 0",
        "有真实失败 → 1",
    ),
    (
        "失败优先于观测缺口（顺序写反）",
        "eval_online.py",
        "    if passed < tested:\n        return 1",
        "    if False:\n        return 1",
        "有失败优先报 1",
    ),
    # ---- 双向判据套件（本轮新增）。注意锚点唯一性：
    # `if is_degraded(text, cost):` 在三个套件里都出现，replace(count=1) 只会
    # 命中最前面的 tool 套件，测不到 answer 套件。用 answer 套件独有的打印行做锚。
    (
        "该答未答不再判失败",
        "eval_online.py",
        "        if must and not any(m in text for m in must):",
        "        if False:",
        "该答未答 → 判失败",
    ),
    (
        "不该出现却出现不再判",
        "eval_online.py",
        "        if forbidden:",
        "        if False:",
        "不该出现却出现 → 判失败",
    ),
    (
        "该拒未拒不判失败",
        "eval_online.py",
        '        if c.get("mustRefuse") and not any(r in text for r in REFUSAL_MARKERS):',
        "        if False:",
        "库里没有却硬答 → 判失败",
    ),
    (
        "answer 套件降级不再跳过",
        "eval_online.py",
        " 降级，不计入（两个方向的断言在空回答上都会失真）')\n            continue",
        " 降级，不计入')",
        "降级 → 不进分母（防 mustContain 空串恒假造成假红）",
    ),
    (
        "安全套件不再落 live-strict",
        "eval_online.py",
        'STRICT_SUITES = {"inject"}',
        'STRICT_SUITES = set()',
        "inject 套件落 live-strict",
    ),
    (
        "record_live 不再校验 kind",
        "eval_results.py",
        '    if kind not in ("live", "live-strict"):',
        "    if False:",
        "record_live 拒绝非法 kind（防静默写错档位）",
    ),
    # ---- RAG 指标与运行清单（本轮新增能力的对应变异）----
    (
        "RAG recall 分母换成返回条数",
        "eval_rag.py",
        "    return len(hits) / len(wanted)",
        "    return len(hits) / max(len(retrieved), 1)",
        "漏检 recall=0.5",
    ),
    (
        "RAG 命中不再按 top-k 截断",
        "eval_rag.py",
        "    for doc in retrieved[:k]:",
        "    for doc in retrieved:",
        "k 之外不算命中",
    ),
    (
        "manifest 指纹退化为常量",
        "eval_manifest.py",
        '        return hashlib.sha256(fh.read()).hexdigest()',
        '        return "0" * 64',
        "sha256 与文件内容一致",
    ),
    (
        "manifest 只扫一层目录",
        "eval_manifest.py",
        "    for dirpath, dirnames, filenames in os.walk(root):",
        "    for dirpath, dirnames, filenames in [(root, [], os.listdir(root))]:",
        "递归指纹到子目录提示词",
    ),
    (
        "runId 退回秒级时间戳",
        "eval_manifest.py",
        '        "runId": f"eval-{stamp}-{secrets.token_hex(2)}",',
        '        "runId": f"eval-{stamp}",',
        "同秒两次 runId 不同",
    ),
    (
        "recall 分母不去重",
        "eval_rag.py",
        "    return len(hits) / len(wanted)",
        "    return len(hits) / len(expected)",
        "expected 重复仍能完全命中",
    ),
    # ---- Wilson 置信区间与用例级 diff（本轮新增判定逻辑）----
    (
        "CI 退回点估计（区间退化为单个值）",
        "eval_baseline.py",
        "    return (max(0.0, center - half), min(1.0, center + half))",
        "    return (p, p)",
        "1/1 全通过下界非退化",
    ),
    (
        "CI 用正态近似越界",
        "eval_baseline.py",
        "    return (max(0.0, center - half), min(1.0, center + half))",
        "    return (p - z * math.sqrt(p * (1 - p) / total) if total else 0.0,\n"
        "            p + z * math.sqrt(p * (1 - p) / total) if total else 0.0)",
        "1/1 全通过下界非退化",
    ),
    (
        "用例级 diff 不再区分新增失败",
        "eval_baseline.py",
        "    return sorted(c - b), sorted(b - c)",
        "    return [], sorted(b - c)",
        "diff 检出新增失败",
    ),
    (
        "case_ids 无 id 时瞎猜",
        "eval_baseline.py",
        '        m = re.match(r"^([A-Za-z0-9_.-]+)(?:\\s|$)", str(f).strip())\n'
        "        if m:\n"
        "            out.add(m.group(1))",
        '        m = re.match(r"^([A-Za-z0-9_.-]+)(?:\\s|$)", str(f).strip())\n'
        "        out.add(m.group(1) if m else str(f).strip()[:8])",
        "无 id 明细不编造",
    ),
]


def run_selftest_in(directory: Path) -> tuple[int, list[str]]:
    """跑指定目录里的 selftest.py 副本（变异施加在该目录的源码副本上）。

    selftest.py 用 `Path(__file__).parent` 定位同目录模块并 sys.path.insert，
    所以副本目录里 selftest 导入的是**被变异的副本模块**，不是 HERE 的原版——
    这正是隔离要成立的关键：变异必须真的影响被测行为。
    """
    p = subprocess.run([sys.executable, str(directory / "selftest.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=SUBPROC_ENV)
    fails = [ln.strip() for ln in p.stdout.splitlines() if ln.strip().startswith("FAIL")]
    return p.returncode, fails


def run_selftest() -> tuple[int, list[str]]:
    """跑源码目录的 selftest（只用于跑前确认基线是绿的；变异阶段走 run_selftest_in）。"""
    p = subprocess.run([sys.executable, str(HERE / "selftest.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=SUBPROC_ENV)
    fails = [ln.strip() for ln in p.stdout.splitlines() if ln.strip().startswith("FAIL")]
    return p.returncode, fails


def main() -> int:
    if "--list" in sys.argv:
        for name, fname, *_ in MUTATIONS:
            print(f"  {name}  ->  {fname}")
        return 0

    _, base_fails = run_selftest()
    if base_fails:
        print("[ERROR] selftest 本身就没过，先修好它再谈变异测试：")
        for f in base_fails:
            print("   - " + f)
        return 2
    print("基线：selftest 全绿\n")

    # 变异施加在**临时工作区副本**上，源文件全程只读——
    # 变异脚本自己就是一个会改写源码的脚本，历史上是"改了再 finally 恢复"。
    # 恢复逻辑再可靠也是兜底：进程被杀在写入与恢复之间，留下的就是坏源码。
    # 复制 selftest.py 是因为 run_selftest 按副本目录定位它。
    undetected = []
    tmpdir = Path(tempfile.mkdtemp(prefix="mutation_"))
    try:
        for fname in sorted({m[1] for m in MUTATIONS} | {"selftest.py"}):
            shutil.copy2(HERE / fname, tmpdir / fname)
        for name, fname, old, new, expect in MUTATIONS:
            path = tmpdir / fname
            src = path.read_text(encoding="utf-8")
            if old not in src:
                print(f"  ?? {name}: 变异点没匹配上（源码已改，需更新 MUTATIONS）")
                undetected.append(name + "（变异未施加）")
                continue
            try:
                path.write_text(src.replace(old, new, 1), encoding="utf-8")
                rc, fails = run_selftest_in(tmpdir)
                if rc == 0 and not fails:
                    print(f"  MISSED  {name}  -> 改坏后仍然全绿，测试有洞")
                    undetected.append(name)
                else:
                    print(f"  caught  {name}  ({len(fails)} 条断言翻红，"
                          f"预期由「{expect}」检出)")
            finally:
                path.write_text(src, encoding="utf-8")  # 副本内恢复，源码从未被碰
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print()
    if undetected:
        print("以下变异未被检出（需要补断言）：")
        for u in undetected:
            print("   - " + u)
        return 1
    print("所有变异都被检出：测试有区分力。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
