#!/usr/bin/env python3
"""评测报告汇总：把分散的 JSON 汇成一份人/机器可读的单一视图。

输入（全部可选，缺哪段就如实标"未提供"，不编造）：
    --baseline-json    基线对比结果（由外部产出；无则跳过该段）
    --rootcause-json   eval_governance.py rootcause 的 --report 输出
    --manifest-a/b     两次运行的 manifest，用于 diff
    --results-dir      eval-results/ 目录，统计分片总数
    --out              输出路径，默认 eval/eval-report.md

设计纪律：
- **只读**：不修改任何输入，不重新判定，不替代任何门禁的 pass/fail。
- 报告里的每个数字都标来源；拿不到就写"未提供"，绝不估算。
- 退出码恒 0（报告生成失败才 1），它不进 CI 门禁链——避免"写报告"变成新的假绿点。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _read_json(path: str | None):
    if not path:
        return None
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def effect_size(rate_before: float, rate_after: float, n_before: int,
                n_after: int) -> dict:
    """两版本通过率差异的效应量与显著性线索（描述性，不是显著性检验）。

    返回绝对差、相对变化、合并标准误下的 z 值。z 只是"值不值得看"的线索，
    不产出 p 值、不做接受/拒绝——判定权始终在 eval_baseline.py 的退出码。
    """
    if n_before <= 0 or n_after <= 0:
        return {"provided": False}
    diff = rate_after - rate_before
    pooled = (rate_before * (1 - rate_before) / n_before
              + rate_after * (1 - rate_after) / n_after)
    se = pooled ** 0.5
    z = diff / se if se > 0 else 0.0
    return {
        "provided": True,
        "absoluteDiff": round(diff, 4),
        "relativeChange": round(diff / rate_before, 4) if rate_before else None,
        "z": round(z, 4),
        "note": "描述性线索，不替代基线门禁判定",
    }


def suggest_threshold(history_rates: list[float], *, margin: float = 0.02) -> dict:
    """基于历史通过率给一个**只读**的阈值建议，绝不自动应用。

    取历史最低值减去 margin 作为候选下限；样本太少时明确说"不足以建议"。
    输出里带 `applied: false`——它不会改任何配置，只供人决定要不要显式写进
    --allow-flip / --min-* 参数。
    """
    if len(history_rates) < 5:
        return {"provided": False, "reason": "历史轮次 < 5，不足以建议阈值",
                "applied": False}
    lo = min(history_rates)
    suggestion = max(0.0, round(lo - margin, 4))
    return {"provided": True, "historyMin": round(lo, 4),
            "suggestedFloor": suggestion, "applied": False,
            "note": "只读建议；是否采用由人显式写入参数"}


def count_shards(results_dir: str | None) -> dict:
    """统计结果目录里的分片（排除汇总文件），纯函数式统计。"""
    if not results_dir or not os.path.isdir(results_dir):
        return {"provided": False, "total": 0}
    files = [f for f in os.listdir(results_dir)
             if f.endswith(".json") and not f.endswith("-results.json")
             and f != "results.json"]
    return {"provided": True, "total": len(files), "files": sorted(files)}


def build_report(*, baseline=None, rootcause=None, manifest_a=None,
                 manifest_b=None, shards=None) -> str:
    """纯函数：生成 Markdown 报告文本。缺哪段标哪段，不编造。"""
    lines = ["# 评测报告", "",
             f"生成时间：{datetime.now().isoformat(timespec='seconds')}", "",
             "> 本报告只汇总已有的外部事实，不重新判定、不替代任何门禁结论。", ""]

    lines += ["## 1. 结果分片", ""]
    if shards and shards.get("provided"):
        lines += [f"- 分片数：{shards['total']}（来源：结果目录）", ""]
        if shards.get("files"):
            lines += ["```"] + shards["files"] + ["```", ""]
    else:
        lines += ["- 未提供（未传 --results-dir 或目录不存在）", ""]

    lines += ["## 2. 基线对比", ""]
    if baseline:
        lines += [f"- 来源：`--baseline-json`", "",
                  "```json", json.dumps(baseline, ensure_ascii=False, indent=2), "```", ""]
    else:
        lines += ["- 未提供（本工具不替代 `eval_baseline.py` 的判定）", ""]

    lines += ["## 3. 根因分层", ""]
    if rootcause:
        by = rootcause.get("by_cause", {})
        lines += [f"- 失败总数：{rootcause.get('total', 0)}；"
                  f"未分类：{rootcause.get('unclassified', 0)}", ""]
        if by:
            lines += ["| 根因 | 条数 |", "|---|---|"]
            for k, v in sorted(by.items()):
                lines.append(f"| {k} | {v} |")
            lines.append("")
    else:
        lines += ["- 未提供", ""]

    lines += ["## 4. 运行指纹差异", ""]
    if manifest_a and manifest_b:
        import eval_manifest as M  # 复用同一 diff 逻辑，不复制真源
        diffs = M.manifest_diff(manifest_a, manifest_b)
        if diffs:
            lines += ["```"] + diffs + ["```", ""]
        else:
            lines += ["- 两份 manifest 无差异", ""]
    else:
        lines += ["- 未提供（需同时传 --manifest-a / --manifest-b）", ""]

    lines += ["## 5. 读法", "",
              "- 本报告的数字来自上面各段标注的来源；缺段即标为未提供。",
              "- 通过/退化/不可判定的结论以 `eval_baseline.py` 的退出码为准。",
              "- 报告本身不设门禁，不产生 pass/fail。", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="评测报告汇总")
    ap.add_argument("--baseline-json")
    ap.add_argument("--rootcause-json")
    ap.add_argument("--manifest-a")
    ap.add_argument("--manifest-b")
    ap.add_argument("--results-dir")
    ap.add_argument("--out", default="eval/eval-report.md")
    ap.add_argument("--json", action="store_true", help="同时输出 JSON 结构")
    args = ap.parse_args()

    baseline = _read_json(args.baseline_json)
    rootcause = _read_json(args.rootcause_json)
    ma, mb = _read_json(args.manifest_a), _read_json(args.manifest_b)
    shards = count_shards(args.results_dir)
    text = build_report(baseline=baseline, rootcause=rootcause,
                        manifest_a=ma, manifest_b=mb, shards=shards)

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"报告已写入：{out}")
    if args.json:
        with open(out + ".json", "w", encoding="utf-8") as fh:
            json.dump({"baseline": baseline, "rootcause": rootcause,
                       "manifestDiff": bool(ma and mb), "shards": shards},
                      fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
