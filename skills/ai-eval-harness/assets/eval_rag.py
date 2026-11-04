#!/usr/bin/env python3
"""RAG 检索层指标：Recall@K / MRR / nDCG@K / Precision@K（判定依据 = 人工标注对）。

数据集形状（每行一个 JSON 对象，放进 eval/datasets/rag-retrieval.jsonl）：
    {"id":"q1","query":"…","expected":["doc1","doc2"],
     "retrieved":["doc3","doc1","doc7"],"k":4}

- expected  人工标注的应命中文档 ID。**这是判定的权威依据**——检索质量
  只对标注对负责，不从模型回答里读。
- retrieved 被测检索系统实际返回的排序列表，由你的检索服务导出（本脚本
  不连接任何检索服务：怎么导出是你的适配层，指标计算是确定性的）。
- k         单用例可省略，默认取 --top-k。

指标是纯函数（recall_at_k / mrr / precision_at_k / ndcg_at_k），
selftest 直接断言它们的值；结果默认按 **offline** kind 落盘：
同一语料、同一索引下检索是确定性的，掉条数就是真掉了。

两道门，语义分开、都诚实：
1. **基线门**：每条用例 pass = 期望文档全部进 top-k（recall@k == 1）。
   分片记录"完全命中条数"，交给 eval_baseline.py 按绝对条数判退化——
   掉 1 条就是检索真退化了，offline 零容忍。
2. **阈值门**（可选）：--min-recall / --min-mrr 设套件级下限，
   低于即退出码 1。不设就只报告（exit 0），把判定留给基线。

退出码：0 有用例且（未设阈值或达标）；1 低于阈值；2 数据集缺失/为空/全坏行。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _ranked(retrieved: list[str], k: int) -> list[str]:
    """截到 top-k，并去掉重复 id（重复只算第一次出现）。"""
    seen: set[str] = set()
    out: list[str] = []
    for doc in retrieved[:k]:
        if doc not in seen:
            seen.add(doc)
            out.append(doc)
    return out


def recall_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """|期望 ∩ top-k| / |期望|。分母永远是标注数，与返回了多少条无关。"""
    if not expected:
        return 0.0
    hits = set(expected) & set(_ranked(retrieved, k))
    return len(hits) / len(expected)


def precision_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """|期望 ∩ top-k| / k。"""
    if k <= 0:
        return 0.0
    hits = set(expected) & set(_ranked(retrieved, k))
    return len(hits) / k


def mrr(expected: list[str], retrieved: list[str], k: int) -> float:
    """第一个命中文档的倒数排名；top-k 内没命中记 0。"""
    ranked = _ranked(retrieved, k)
    expected_set = set(expected)
    for i, doc in enumerate(ranked, start=1):
        if doc in expected_set:
            return 1.0 / i
    return 0.0


def ndcg_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """二元相关增益的 nDCG@K。"""
    if not expected or k <= 0:
        return 0.0
    ranked = _ranked(retrieved, k)
    expected_set = set(expected)
    dcg = sum(1.0 / math.log2(i + 1) for i, doc in enumerate(ranked, start=1)
              if doc in expected_set)
    ideal_len = min(len(expected), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_len + 1))
    return dcg / idcg if idcg > 0 else 0.0


def load_cases(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"找不到数据集：{path}\n"
                         f"请从 assets/datasets/rag-retrieval.example.jsonl 复制改写。")
    cases: list[dict] = []
    bad = 0
    # utf-8-sig：兼容 PowerShell Out-File 生成的 BOM 头（实测 BOM 会让
    # 首行 json.loads 失败，整份"看起来为空"）；对无 BOM 文件零影响。
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not isinstance(obj, dict) or not obj.get("id") \
                    or not isinstance(obj.get("expected"), list) \
                    or not isinstance(obj.get("retrieved"), list):
                bad += 1
                continue
            cases.append(obj)
    if bad:
        print(f"[WARN] {bad} 行无法解析（缺 id/expected/retrieved），已跳过")
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 检索层指标")
    ap.add_argument("--dataset", default=os.path.join("eval", "datasets", "rag-retrieval.jsonl"))
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--min-recall", type=float, default=None,
                    help="套件平均 Recall@K 下限，低于则退出 1（可选）")
    ap.add_argument("--min-mrr", type=float, default=None,
                    help="套件平均 MRR 下限，低于则退出 1（可选）")
    ap.add_argument("--record", action="store_true",
                    help="把完全命中条数按 offline kind 落盘，供基线对比")
    args = ap.parse_args()

    cases = load_cases(args.dataset)
    if not cases:
        print("[ERROR] 没有可计算的用例（数据集为空或全部坏行），本轮不可判定。")
        return 2

    per_case: list[dict] = []
    full_hits = 0
    failures: list[str] = []
    for c in cases:
        k = int(c.get("k") or args.top_k)
        exp, ret = c["expected"], c["retrieved"]
        r = recall_at_k(exp, ret, k)
        row = {
            "id": c["id"], "k": k,
            "recall": round(r, 4),
            "precision": round(precision_at_k(exp, ret, k), 4),
            "mrr": round(mrr(exp, ret, k), 4),
            "ndcg": round(ndcg_at_k(exp, ret, k), 4),
        }
        per_case.append(row)
        if r == 1.0:
            full_hits += 1
        else:
            misses = sorted(set(exp) - set(_ranked(ret, k)))
            failures.append(f'{c["id"]} recall@{k}={r:.2f} 漏检={misses}')

    n = len(per_case)
    mean = {
        "recall": sum(x["recall"] for x in per_case) / n,
        "precision": sum(x["precision"] for x in per_case) / n,
        "mrr": sum(x["mrr"] for x in per_case) / n,
        "ndcg": sum(x["ndcg"] for x in per_case) / n,
    }

    print(f"\n用例 {n} 条（top-k 默认 {args.top_k}）")
    for row in per_case:
        print(f'  {row["id"]:<14} recall@{row["k"]}={row["recall"]:.2f} '
              f'P={row["precision"]:.2f} MRR={row["mrr"]:.2f} nDCG={row["ndcg"]:.2f}')
    print(f"\n套件平均：Recall={mean['recall']:.3f}  Precision={mean['precision']:.3f}  "
          f"MRR={mean['mrr']:.3f}  nDCG={mean['ndcg']:.3f}")
    print(f"完全命中（期望全部进 top-k）：{full_hits}/{n}")

    if args.record:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import eval_results  # noqa: PLC0415
            path = eval_results.record("RAG 检索", full_hits, n, failures)
            print(f"  已记录（offline，基线按完全命中条数判退化）: {path}")
        except ImportError:
            print("  (未找到 eval_results.py，跳过落盘)")

    if failures:
        print("\n未完全命中的用例：")
        for f in failures:
            print(f"  - {f}")

    if args.min_recall is not None and mean["recall"] < args.min_recall:
        print(f"[FAIL] 平均 Recall {mean['recall']:.3f} < 阈值 {args.min_recall}")
        return 1
    if args.min_mrr is not None and mean["mrr"] < args.min_mrr:
        print(f"[FAIL] 平均 MRR {mean['mrr']:.3f} < 阈值 {args.min_mrr}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
