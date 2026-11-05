#!/usr/bin/env python3
"""评测治理三件套：根因分层 / 数据集治理 / Judge 校准。

三者都是**确定性计算**，判定依据来自结构化输入（外部事实），不用模型互评。

1) classify_root_cause()  根因分层（SKILL.md 八类表）
   输入一条失败明细，返回根因标签。规则式分类，判不了的返回 "unclassified"
   而不是硬塞一个类别——猜错类别比不分类更误导。

2) validate_dataset()     数据集治理
   唯一 ID、必填字段、正反向覆盖、三集隔离（调试/验证/冻结），
   frozen 集只读校验（对比基准哈希，改了就红）。

3) judge_agreement()      LLM Judge 校准
   算 Judge 与人工标注的一致率（Cohen's kappa 的简化版：一致率 + 期望一致率）。
   低于阈值（默认 0.8）或标注样本太少（< 20）时**禁止 Judge 进门禁**——
   这正对应 SKILL.md「三级判定：Judge 只进第三级，且必须有人工标注集背书」。

CLI：
    python eval_governance.py rootcause --failures failures.json --report out.json
    python eval_governance.py dataset  --dir eval/datasets --frozen-hash frozen.json
    python eval_governance.py judge    --labels judge-labels.json --min-agreement 0.8
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT_CAUSES = ("数据问题", "检索问题", "切片问题", "提示词问题",
               "模型问题", "工具问题", "评测问题", "基础设施问题")

# 关键词 → 类别。按 SKILL.md 的八类表，命中即归类；多命中取第一个。
_CAUSE_RULES = [
    ("基础设施问题", ("超时", "限流", "余额", "402", "401", "网络", "连接失败", "token 耗尽")),
    ("评测问题", ("判据", "期望值", "错误跳过", "mustContain", "mustNotContain", "误报", "漏报", "基线", "分母")),
    ("数据问题", ("知识库过期", "内容过期", "文档冲突", "互相冲突", "数据不一致")),
    ("检索问题", ("未召回", "召回", "排序靠后", "漏检", "Recall")),
    ("切片问题", ("切散", "切片边界", "截断", "articleId")),
    ("提示词问题", ("规则冲突", "提示词冲突", "禁止回答", "不得回答")),
    ("工具问题", ("参数错", "执行失败", "幂等", "越权调用", "重复调用")),
    ("模型问题", ("幻觉", "编造", "推理错误", "极性答反", "答反")),
]


def classify_root_cause(failure: str) -> str:
    """单条失败明细的根因标签。判不了返回 "unclassified"，不猜。"""
    text = str(failure)
    for cause, keywords in _CAUSE_RULES:
        if any(k in text for k in keywords):
            return cause
    return "unclassified"


def summarize_root_causes(failures: list[str]) -> dict:
    """统计各层失败数。unclassified 单独报，不混入任何层。"""
    counts = Counter(classify_root_cause(f) for f in failures)
    return {"by_cause": dict(counts), "total": len(failures),
            "unclassified": counts.get("unclassified", 0)}


# ---------------------------------------------------------------- 数据集治理

REQUIRED_FIELDS = ("id", "why")
SPLITS = ("dev", "validation", "frozen")


def validate_dataset(cases: list[dict], *, frozen_hash: str | None = None) -> list[str]:
    """数据集治理校验，返回违规清单（空 = 合规）。"""
    bad: list[str] = []
    seen: set[str] = set()
    has_positive = has_negative = False
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            bad.append(f"第 {i+1} 行不是对象")
            continue
        cid = c.get("id")
        if not cid:
            bad.append(f"第 {i+1} 行缺 id")
        elif cid in seen:
            bad.append(f"重复 id：{cid}（改语义应换新 id，不复用）")
        else:
            seen.add(cid)
        for f in REQUIRED_FIELDS:
            if f == "id":
                continue
            if not c.get(f):
                bad.append(f"{cid or i+1} 缺必填字段 {f}")
        if c.get("mustContain") or c.get("expected"):
            has_positive = True
        if c.get("mustRefuse") or c.get("mustNotContain"):
            has_negative = True
        split = c.get("split")
        if split is not None and split not in SPLITS:
            bad.append(f"{cid} split={split!r} 非法（应为 {SPLITS}）")
    if not has_positive:
        bad.append("数据集没有正向用例（只测单向，分数能刷高）")
    if not has_negative:
        bad.append("数据集没有反向用例（测不出编造/越权）")
    if frozen_hash is not None:
        actual = hashlib.sha256(
            json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if actual != frozen_hash:
            bad.append("冻结集内容被改动（frozen 只读，改需换版本号并写明原因）")
    return bad


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as fh:
        out = []
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # 注释行：样例文件常带说明，不该被当成坏 JSON
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # 不静默吞掉坏行：真实数据集里坏行意味着用例丢了，报出来
                print(f"[WARN] {path} 有无法解析的行，已跳过：{line[:60]}")
        return out


# ---------------------------------------------------------------- Judge 校准

def judge_agreement(labels: list[dict], min_agreement: float = 0.8,
                    min_samples: int = 20) -> dict:
    """Judge 与人工标注的一致性。低于门槛 → gate=False（禁止 Judge 进门禁）。

    labels: [{"human": "pass", "judge": "pass"}, ...]，二值或任意字符串标签。
    返回一致率、kappa、样本数、是否放行，以及**为什么不放行**。
    """
    n = len(labels)
    agree = sum(1 for x in labels if x.get("human") == x.get("judge"))
    rate = agree / n if n else 0.0
    human_pos = sum(1 for x in labels if x.get("human") in ("pass", "yes", True))
    judge_pos = sum(1 for x in labels if x.get("judge") in ("pass", "yes", True))
    p_h = human_pos / n if n else 0.0
    p_j = judge_pos / n if n else 0.0
    expected = p_h * p_j + (1 - p_h) * (1 - p_j)
    kappa = (rate - expected) / (1 - expected) if expected < 1 else 0.0
    reasons = []
    if n < min_samples:
        reasons.append(f"标注样本 {n} < {min_samples}，不足以校准")
    if rate < min_agreement:
        reasons.append(f"一致率 {rate:.3f} < {min_agreement}")
    return {"samples": n, "agreement": round(rate, 4),
            "kappa": round(kappa, 4), "gate": not reasons,
            "reasons": reasons or ["一致率达标，可作为辅助分（仍不单独决定门禁）"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="评测治理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("rootcause", help="失败明细根因分层")
    p1.add_argument("--failures", required=True, help="失败明细 JSON（字符串数组）")
    p1.add_argument("--report", default=None)

    p2 = sub.add_parser("dataset", help="数据集治理校验")
    p2.add_argument("--dir", required=True, help="数据集目录（*.jsonl）")
    p2.add_argument("--frozen-hash", default=None, help="冻结集基准 sha256")

    p3 = sub.add_parser("judge", help="Judge 校准")
    p3.add_argument("--labels", required=True, help="人工/Judge 标注对 JSON 数组")
    p3.add_argument("--min-agreement", type=float, default=0.8)
    p3.add_argument("--min-samples", type=int, default=20)

    args = ap.parse_args()

    if args.cmd == "rootcause":
        failures = json.load(open(args.failures, encoding="utf-8-sig"))
        report = summarize_root_causes(failures)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        return 1 if report["unclassified"] == report["total"] and report["total"] else 0

    if args.cmd == "dataset":
        cases = []
        for name in sorted(os.listdir(args.dir)):
            if name.endswith(".jsonl"):
                cases += load_jsonl(os.path.join(args.dir, name))
        bad = validate_dataset(cases, frozen_hash=args.frozen_hash)
        if bad:
            for b in bad:
                print(f"[FAIL] {b}")
            return 1
        print(f"[PASS] {len(cases)} 条用例，正反向覆盖、唯一 ID、必填字段、三集隔离均合规")
        return 0

    if args.cmd == "judge":
        labels = json.load(open(args.labels, encoding="utf-8-sig"))
        r = judge_agreement(labels, args.min_agreement, args.min_samples)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["gate"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
