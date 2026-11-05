#!/usr/bin/env python3
"""通用评测基线对比：结果 vs 基线，退化即非零退出。产物就是 CI 卡点。

与具体项目解耦：只认一种很窄的数据形状，任何语言/框架产出的结果都能接入。

输入形状（二者皆可）
-------------------
1) 目录：其中每个 *.json 都是下面两种之一
2) 单文件

单个 suite 的形状：
    {"suite": "PII 脱敏", "passed": 13, "total": 13, "kind": "offline",
     "failures": ["g34 未挂门禁"]}
或一个列表：[{...}, {...}]

判退化用**绝对条数**，不用比率
------------------------------
比率为分母服务，小样本上会说谎：8 条里翻 1 条就是 12.5 个百分点，
而 13 条里掉 1 条是 7.7 个百分点——同一个事实，两个数字，都不可比。
"掉了几条"与分母无关，才是可跨数据集比较的量。

按 kind 分严格度
----------------
    offline      纯函数，同一输入必同一输出。掉 1 条就是真掉了，容忍 0 条。
    live-strict  安全/编造类门禁（提示词泄漏、PII、越权、编造数字）。
                 随机性不是豁免理由：随机安全失败放到线上就是随机事故，容忍 0 条。
    live         普通能力类，真打模型有随机性。默认容忍 1 条波动（--allow-flip 可调）。

用法
----
    python eval_baseline.py --results out/ --baseline eval/baseline.json
    python eval_baseline.py --results out/ --baseline eval/baseline.json --update
    python eval_baseline.py --results out/ --baseline eval/baseline.json --strict

退出码
------
    0  无退化
    1  检出退化（有 suite 掉出容忍范围）
    2  **本轮结果不可判定**：读不到输入，或有 suite 的分母与基线不一致
       与 1 分开是有意的——2 的意思是"别拿这个当退化去查产品，先把基线重建"，
       报 0 会让分母变化后的第一次运行看起来"全绿"。

为什么分母变化不判退化
----------------------
数据集从 13 条扩到 20 条后，新旧比率本来就不可比；此时任何判定（通过或退化）
都是编出来的。必须人工核对失败明细后 --update 重建基线。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

# Windows 下 stdout 被重定向（CI 捕获、tee、> 文件）时按本地码页 GBK 编码，
# 打印中文/替换符会直接 UnicodeEncodeError 崩掉——门禁在 CI 里必崩、只在交互终端能用。
# 显式改成 UTF-8；errors="replace" 保证极端情况下也只是丢字形，不会中断判定。
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CONSOLIDATED_NAME = "results.json"

# 各 kind 的默认容忍波动条数。offline=0 是硬要求：纯函数不该有波动，
# 出现波动说明判据不稳定（依赖时间、随机数、未固定的词典顺序），那是更该修的问题。
# live-strict=0：安全类门禁（泄漏/PII/越权/编造）不存在"允许波动 1 条"——
# 在线模型的随机性只解释能力波动，解释不了"这一次它把提示词说出去了"。
DEFAULT_ALLOW_FLIP = {"offline": 0, "live-strict": 0, "live": 1}

# 百分比仅供参考的分界线。低于 MIN_CONCLUSIVE 时明确标"不足以支撑结论"，
# 避免把 "1/1 = 100%" 这种没有信息量的数字当成质量证据。
ANNOTATE_BELOW = 10
MIN_CONCLUSIVE = 5


def _infer_kind(entry: dict, source: str) -> str:
    """kind 优先取字段；没有则从分片文件名前缀推；再没有按 offline（最严格）。

    文件名兜底是必要的：外部项目手写的结果文件常常没有 kind，
    默认成 live（容忍 1 条）会让离线评测悄悄放过退化。
    live- / live-strict- 前缀都能从文件名推出；live-strict 更靠前匹配。
    """
    kind = entry.get("kind")
    if isinstance(kind, str) and kind in DEFAULT_ALLOW_FLIP:
        return kind
    base = os.path.basename(source)
    if base.startswith("live-strict-"):
        return "live-strict"
    if base.startswith("live-"):
        return "live"
    return "offline"


def _coerce(entry: dict, source: str) -> dict | None:
    """把一条记录规整成统一结构；不合规返回 None。"""
    if not isinstance(entry, dict):
        return None
    name = entry.get("suite") or entry.get("name") or entry.get("id")
    passed, total = entry.get("passed"), entry.get("total")
    if name is None or passed is None or total is None:
        return None
    try:
        return {
            "suite": str(name),
            "passed": int(passed),
            "total": int(total),
            "kind": _infer_kind(entry, source),
            "failures": [str(f) for f in (entry.get("failures") or [])],
        }
    except (TypeError, ValueError):
        return None


def load_results(path: str, *, exclude: str | None = None) -> dict[str, dict]:
    """读目录或单文件，合并成 suite -> 结果记录。

    单文件支持三种形状：
    - 单个 suite：{"suite","passed","total"}
    - suite 列表：[{...}, {...}]
    - consolidate() 产出：{"suites": {name: {...}, ...}}

    exclude 传基线文件的绝对路径：有人会把 base.json 丢在结果目录里，
    那会被当成本次结果读进来，污染通过率。
    """
    files: list[str] = []
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if not name.endswith(".json") or _is_consolidated(name):
                # 目录模式忽略合并文件（consolidate 的产物）。它排在分片之后被读取，
                # 若内容是上一次合并的旧值，会把新分片覆盖掉——旧数据盖新数据的静默错误。
                # 判据必须是 _is_consolidated 而不是只认 results.json：
                # 真实项目的 Java 版把汇总写成 offline-results.json，
                # 只认 results.json 时它会被当普通分片读进来，静默盖掉本次新结果。
                continue
            full = os.path.abspath(os.path.join(path, name))
            if exclude and full == exclude:
                continue
            files.append(full)
    elif os.path.isfile(path):
        files.append(path)
        # 只有合并快照才警告。条件要卡在这个判断上：
        # 实测误报过一次——把同目录的 base.json 当单文件读时也被提示"快照已过期"，
        # 基线不是快照，用户会以为自己的基线坏了。
        if _is_consolidated(os.path.basename(path)):
            parent = os.path.dirname(os.path.abspath(path))
            shards = [n for n in os.listdir(parent)
                      if n.startswith(("offline-", "live-")) and n.endswith(".json")]
            if shards:
                print(f"[WARN] {path} 是同目录 {len(shards)} 个分片的快照，可能已过期；"
                      f"要读最新结果请传目录：{parent}")
    else:
        raise FileNotFoundError(path)

    suites: dict[str, dict] = {}
    for fp in files:
        # utf-8-sig：容忍 PowerShell/手写编辑器产生的 BOM；无 BOM 零影响
        with open(fp, encoding="utf-8-sig") as fh:
            data = json.load(fh)

        # consolidate() 的 {"suites": {...}} 形状：先把内层取出来
        if isinstance(data, dict) and "suites" in data and "suite" not in data:
            inner = data["suites"]
            entries = list(inner.values()) if isinstance(inner, dict) else inner
        else:
            entries = data if isinstance(data, list) else [data]

        for entry in entries:
            got = _coerce(entry, fp)
            if got:
                suites[got["suite"]] = got
    return suites


def _is_consolidated(name: str) -> bool:
    """识别"合并快照"文件：results.json 或 <前缀>-results.json。

    只认 results.json 不够——真实项目里 Java 版把汇总写成
    `offline-results.json`，它排在分片之后被读入，会用上一次的快照
    覆盖本次新分片，且完全静默。
    """
    return name == CONSOLIDATED_NAME or name.endswith("-results.json")


def load_baseline(path: str) -> dict[str, dict]:
    """读基线。兼容四种写法。

    兼容性要真的实现，不能只写在文档里——本函数曾声称支持 `[p, t]` 列表形状，
    实际只认 dict，列表被静默丢弃，等于"文档说 X、代码做 Y"。

        {"suites": {name: {passed,total,...}}}     推荐
        {"suites": [ {suite,passed,total,...} ]}
        {"results": [ {suite,passed,total,...} ]}  部分项目的历史形状
        {name: {passed,total,...}} 或 {name: [passed,total]}
    """
    with open(path, encoding="utf-8-sig") as fh:
        raw = json.load(fh)

    entries: list[dict] = []
    if isinstance(raw, dict) and isinstance(raw.get("suites"), list):
        entries = raw["suites"]
    elif isinstance(raw, dict) and isinstance(raw.get("suites"), dict):
        entries = [{**v, "suite": k} for k, v in raw["suites"].items()
                   if isinstance(v, dict)]
    elif isinstance(raw, dict) and isinstance(raw.get("results"), list):
        entries = raw["results"]
    elif isinstance(raw, dict):
        # 裸映射：值可能是 dict，也可能是 [passed, total]
        entries = []
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                entries.append({**v, "suite": k})
            elif isinstance(v, (list, tuple)) and len(v) == 2:
                entries.append({"suite": k, "passed": v[0], "total": v[1]})

    out: dict[str, dict] = {}
    for e in entries:
        got = _coerce(e, path)
        if got:
            out[got["suite"]] = got
    return out


def suffix(rec: dict) -> str:
    """小样本标注。百分比在 n<10 时只是计数的另一种写法，n<5 时没有结论价值。"""
    t = rec["total"]
    if t < MIN_CONCLUSIVE:
        return f"  (n<{MIN_CONCLUSIVE}，不足以支撑结论)"
    if t < ANNOTATE_BELOW:
        return "  (n<10，百分比仅供参考)"
    return ""


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """通过率的 Wilson score 95% 置信区间（闭式解，无 scipy 依赖）。

    为什么不用正态近似 (p ± z*sqrt(p(1-p)/n))：小样本或 p 接近 0/1 时，
    它会越出 [0,1] 且宽度失真——而本工具最常遇到的正是小 n。
    Wilson 区间在全通过 (p=1) 时仍给出非退化的下界，正好回答"1/1=100% 能信吗"。

    抽成纯函数是为了能被 selftest 直接断言，而不是 inline 在 main() 里凭信心改。
    """
    if total <= 0:
        return (0.0, 0.0)
    p = passed / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return (max(0.0, center - half), min(1.0, center + half))


def case_ids(failures: list[str]) -> set[str]:
    """从失败明细里抠出用例 ID，供用例级 diff 使用。

    约定：失败明细以 case id 开头（如 "a1 该答未答…"、"g34 未挂门禁"）。
    取首段 [A-Za-z0-9_.-]+ 作为 id；抽不出 id 的条目跳过，绝不猜——
    猜错 id 会把"新增失败"报成"修复了"，比不做 diff 更糟。
    """
    out: set[str] = set()
    for f in failures or []:
        m = re.match(r"^([A-Za-z0-9_.-]+)(?:\s|$)", str(f).strip())
        if m:
            out.add(m.group(1))
    return out


def case_diff(base_failures: list[str], cur_failures: list[str]) -> tuple[list[str], list[str]]:
    """用例级差异：(新增失败, 已修复)。两个集合都按 id 排序，输出稳定可比对。

    汇总数字（掉 1 条）只说"总量变了"，diff 才说明"是哪几条"——
    这正是评审里"固定测试集 + 用例级差异比较"要的东西。
    """
    b, c = case_ids(base_failures), case_ids(cur_failures)
    return sorted(c - b), sorted(b - c)


def main() -> int:
    ap = argparse.ArgumentParser(description="评测基线对比")
    ap.add_argument("--results", required=True, help="结果目录或单文件")
    ap.add_argument("--baseline", required=True, help="基线 json 路径")
    ap.add_argument("--update", action="store_true", help="用本次结果覆盖基线")
    ap.add_argument("--allow-flip", type=int, default=None,
                    help="允许的波动条数；不传则按 kind 取默认"
                         "（offline 0 / live-strict 0 / live 1）")
    ap.add_argument("--strict", action="store_true",
                    help="基线里有、本次缺失的 suite 也算失败（默认只提示）")
    args = ap.parse_args()

    try:
        current = load_results(args.results,
                               exclude=os.path.abspath(args.baseline))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[ERROR] 读不到结果：{exc}")
        return 2
    if not current:
        print(f"[ERROR] {args.results} 里没有可识别的 suite")
        return 2

    if args.update:
        payload = {"suites": {
            k: {"passed": v["passed"], "total": v["total"],
                "kind": v["kind"], "failures": v["failures"]}
            for k, v in sorted(current.items())}}
        os.makedirs(os.path.dirname(os.path.abspath(args.baseline)) or ".", exist_ok=True)
        with open(args.baseline, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"已写入基线：{args.baseline}（{len(current)} 项）")
        return 0

    try:
        baseline = load_baseline(args.baseline)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[ERROR] 读不到基线：{exc}（首次使用请加 --update 生成）")
        return 2

    failures: list[str] = []
    notes: list[str] = []
    undecided = 0
    # 退化的 suite 名单独收集，不要拿名字去 failures 的文本里做子串匹配：
    # 套件名互为前缀时（"A" 与 "A 强化"）会误挂明细，红的时候指错地方。
    failed_names: set[str] = set()

    print(f"\n本次结果：{len(current)} 项")
    for name in sorted(current):
        cur = current[name]
        base = baseline.get(name)
        p, t = cur["passed"], cur["total"]
        mark = ""
        if base is None:
            notes.append(f"新增评测「{name}」：{p}/{t}（基线无此项，不判退化）")
        elif base["total"] != t:
            # 分母变了就不可比，任何判定都是编的。强制人工重建基线，而不是猜一个结论。
            undecided += 1
            mark = "  ← 分母变化，本轮不判定"
            notes.append(
                f"「{name}」分母 {base['total']} → {t}；"
                f"核对失败明细后用 --update 重建基线")
        else:
            drop = base["passed"] - p
            allow = args.allow_flip if args.allow_flip is not None \
                else DEFAULT_ALLOW_FLIP.get(cur["kind"], 0)
            # 用例级 diff：只在有失败明细时算；抽不出 id 就如实不报，不猜
            new_failed, fixed = case_diff(base["failures"], cur["failures"])
            if new_failed or fixed:
                notes.append(f"「{name}」用例级变化：新增失败={new_failed or '无'}，"
                             f"已修复={fixed or '无'}")
            if drop > allow:
                mark = "  ← 退化"
                failed_names.add(name)
                failures.append(f"{name}[{cur['kind']}]：{base['passed']}/{t} → {p}/{t}"
                                f"（掉 {drop} 条，容忍 {allow}）")
            elif drop > 0:
                # 在线评测掉 1 条通常是随机波动，但必须留下痕迹：
                # 悄悄容忍 = 把波动攒成真正的退化也一并吞掉
                mark = f"  ← 波动 {drop} 条（容忍内）"
                notes.append(f"「{name}」掉 {drop} 条，在 {cur['kind']} 容忍范围内，"
                             f"连续多轮出现同一条则应当真")
            elif drop < 0:
                notes.append(f"「{name}」提升 {-drop} 条，可考虑更新基线")
        lo, hi = wilson_interval(p, t)
        print(f"  {name:<16} {p}/{t} = {p / t if t else 0:.1%}"
              f"  95%CI=[{lo:.1%},{hi:.1%}]{suffix(cur)}{mark}")

    for name in sorted(set(baseline) - set(current)):
        msg = f"基线有、本次缺失「{name}」（{baseline[name]['passed']}/{baseline[name]['total']}）"
        (failures if args.strict else notes).append(msg)

    print(f"\n基线：{os.path.basename(args.baseline)}（{len(baseline)} 项）")
    if notes:
        print("\n提示：")
        for n in notes:
            print(f"  · {n}")
    print("\n=== 对比结果 ===")
    if failures:
        for f in failures:
            print(f"  [FAIL] 检出退化：{f}")
        # 红的时候必须自带可行动信息：到底是哪几条挂了。
        # 让人再跑一次或去翻日志的卡点，第一次就会被绕开。
        # 用 failed_names 精确匹配，不用 `name in f` 子串匹配——
        # 套件名互为前缀时（"A" 与 "A 强化"）会把明细挂到错的套件上。
        detail = [(n, current[n]["failures"]) for n in sorted(failed_names)
                  if n in current and current[n]["failures"]]
        if detail:
            print("  失败明细：")
            for name, fs in detail:
                print(f"    {name}:")
                for x in fs[:10]:
                    print(f"      - {x}")
                if len(fs) > 10:
                    print(f"      …另有 {len(fs) - 10} 条")
        return 1
    if undecided:
        print(f"  [UNDECIDED] {undecided} 项分母与基线不一致，本轮不可判定。"
              f"请核对后 --update 重建基线。")
        return 2
    print("  [PASS] 无退化。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
