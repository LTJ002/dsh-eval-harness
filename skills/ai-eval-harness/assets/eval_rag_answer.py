#!/usr/bin/env python3
"""RAG 生成层指标：Faithfulness / Citation Correctness / Answer Completeness。

第一原则约束
------------
本脚本**不调用任何模型**给答案打分。判定依据全部来自人工标注对（外部事实）：
    supportFacts   答案里每句应能追溯到的知识库事实（支撑句）
    citations      每个结论应引用的文档 id
    supportingDocs 检索/标注记录里真实存在的支撑文档 id 集合（外部事实）
    citedDocs      答案里实际提到的文档 id（由系统/标注给出，不从中文里猜）
    requiredPoints 必答要点（缺一个就不完整）
    contradictions 与该答案矛盾的已知事实（含符号/单位错误）

数据集形状（一行一用例，eval/datasets/rag-answer.jsonl）：
    {"id":"g1","answer":"需提前 48 小时申请，加收 10% 费用。",
     "supportFacts":["改期需提前 48 小时","改期加收 10% 服务费"],
     "citations":["policy-appointment"],
     "supportingDocs":["policy-appointment"],
     "requiredPoints":["48"],
     "contradictions":["不需要提前"]}

指标（全部确定性纯函数）：
    faithfulness     答案中的数字/事实是否能在 supportFacts 找到依据（无依据=幻觉）
    citation_ok      声明的引用是否真的支撑对应结论（引而不支=不合格）
    completeness     requiredPoints 覆盖比例；缺项直接点名
    contradiction    答案是否命中已知矛盾形态（极性答反/符号错）

两道门：
1. 基线门：每条用例 pass = 三项全达标，进 offline 基线零容忍；
2. 阈值门：--min-faithfulness / --min-completeness，低于即退出 1，且不落盘。

退出码：0 通过 / 1 低于阈值或存在硬违规 / 2 数据集缺失或为空。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

_NUMBER = re.compile(r"([+-]?)\s*(\d[\d,]*(?:\.\d+)?)\s*(%|个百分点)?")


def numbers_of(text: str) -> list[str]:
    """抽出文本里的数字符号串（含 % 与千分位归一化），用于事实溯源。

    "10 %" 与 "10%" 是表示差异，不是事实差异——按 SKILL.md 陷阱一，
    归一化只修表示、不吞语义，这里把两者统一成 "10%"。
    """
    out = []
    for m in _NUMBER.finditer(text):
        sign, raw, unit = m.group(1), m.group(2), m.group(3) or ""
        out.append((sign + raw.replace(",", "") + unit))
    return out


def check_faithfulness(answer: str, support_facts: list[str]) -> list[str]:
    """答案里的每个数字都要能在支撑句里找到；找不到就是无依据（幻觉/编造）。

    只查数字不查整句语义：整句相似度需要模型互评，违反第一原则。
    数字型事实是 RAG 里最常出事故、也最能确定性判定的一类。
    """
    bad: list[str] = []
    haystack = set()
    for f in support_facts:
        haystack.update(numbers_of(str(f)))
    for n in numbers_of(answer):
        if n not in haystack:
            bad.append(f"无依据数字 {n}（支撑句里找不到）")
    return bad


def check_citations(answer: str, citations: list[str],
                    supporting_docs: list[str] | None = None,
                    cited_docs: list[str] | None = None) -> list[str]:
    """引用准确性：声明引用的文档必须真的在支撑文档集合里。

    supporting_docs 来自检索/标注记录（外部事实）。传 None 时只报告"无法核对"
    并判为不合格——引而不支不能因为"没给数据"就算通过。
    cited_docs 是答案里实际提到的文档 id（由你的系统/标注提供）；不用正则
    从中文里猜——"根据政策文档"里的"政策文档"是普通名词，猜成 doc id 会误报。
    """
    bad: list[str] = []
    if not citations:
        return bad  # 没要求引用，不判
    if supporting_docs is None:
        return ["声明了引用但无 supporting_docs，无法核对（不默认通过）"]
    missing = [c for c in citations if c not in supporting_docs]
    if missing:
        bad.append(f"引用不支撑：{missing} 不在支撑文档里")
    for c in (cited_docs or []):
        if c not in supporting_docs:
            bad.append(f"答案提到 {c} 但无该支撑文档")
    return bad


def check_completeness(answer: str, required_points: list[str]) -> list[str]:
    """完整性：必答要点逐项检查，缺哪个点名哪个。"""
    return [f"遗漏要点 {p!r}" for p in required_points if str(p) not in answer]


def check_contradictions(answer: str, contradictions: list[str]) -> list[str]:
    """矛盾检测：答案命中已知矛盾形态即失败（极性答反/符号错等）。"""
    return [f"命中矛盾形态 {c!r}" for c in contradictions if str(c) in answer]


def check_answer(case: dict) -> list[str]:
    """单用例四项汇总，返回失败原因列表（空 = 通过）。纯函数，可断言。"""
    answer = str(case.get("answer") or "")
    bad: list[str] = []
    bad += check_faithfulness(answer, case.get("supportFacts") or [])
    bad += check_citations(answer, case.get("citations") or [],
                           case.get("supportingDocs"), case.get("citedDocs"))
    bad += check_completeness(answer, case.get("requiredPoints") or [])
    bad += check_contradictions(answer, case.get("contradictions") or [])
    return bad


def load_cases(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"找不到数据集：{path}\n"
                         f"请从 assets/datasets/rag-answer.example.jsonl 复制改写。")
    cases, bad = [], 0
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # 注释行
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not isinstance(obj, dict) or not obj.get("id") or "answer" not in obj:
                bad += 1
                continue
            cases.append(obj)
    if bad:
        print(f"[WARN] {bad} 行无法解析（缺 id/answer），已跳过")
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 生成层指标")
    ap.add_argument("--dataset", default=os.path.join("eval", "datasets", "rag-answer.jsonl"))
    ap.add_argument("--min-faithfulness", type=float, default=None,
                    help="套件级：无依据数字用例占比上限的下限分数（可选）")
    ap.add_argument("--min-completeness", type=float, default=None)
    ap.add_argument("--record", action="store_true", help="完全达标条数落盘（offline）")
    args = ap.parse_args()

    cases = load_cases(args.dataset)
    if not cases:
        print("[ERROR] 没有可计算的用例，本轮不可判定。")
        return 2

    full_pass = 0
    faithful = complete = 0
    failures: list[str] = []
    for c in cases:
        bad = check_answer(c)
        if not check_faithfulness(str(c.get("answer") or ""),
                                  c.get("supportFacts") or []):
            faithful += 1
        if not check_completeness(str(c.get("answer") or ""),
                                  c.get("requiredPoints") or []):
            complete += 1
        if not bad:
            full_pass += 1
        else:
            failures.append(f'{c["id"]} {"; ".join(bad)}')

    n = len(cases)
    f_rate, c_rate = faithful / n, complete / n
    print(f"\n用例 {n} 条")
    print(f"  忠实度（无依据数字用例为 0 的比例）：{f_rate:.3f}")
    print(f"  完整性（必答要点齐全的比例）      ：{c_rate:.3f}")
    print(f"  四项全达标：{full_pass}/{n}")
    if failures:
        print("\n未达标用例：")
        for f in failures:
            print(f"  - {f}")

    gate_failed = []
    if args.min_faithfulness is not None and f_rate < args.min_faithfulness:
        gate_failed.append(f"忠实度 {f_rate:.3f} < {args.min_faithfulness}")
    if args.min_completeness is not None and c_rate < args.min_completeness:
        gate_failed.append(f"完整性 {c_rate:.3f} < {args.min_completeness}")
    # 硬违规：无依据数字 / 矛盾形态是安全类，不受阈值豁免
    hard = [f for f in failures if "无依据数字" in f or "命中矛盾形态" in f]
    if hard:
        gate_failed.append(f"{len(hard)} 条硬违规（无依据/矛盾），零容忍")
    if gate_failed:
        if args.record:
            print("\n[SKIP 落盘] 本轮判定失败，不作为基线输入。")
        for m in gate_failed:
            print(f"[FAIL] {m}")
        return 1

    if args.record:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import eval_results  # noqa: PLC0415
            p = eval_results.record("RAG 生成质量", full_pass, n, failures)
            print(f"\n  已记录（offline）: {p}")
        except ImportError:
            print("\n  (未找到 eval_results.py，跳过落盘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
