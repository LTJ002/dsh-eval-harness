#!/usr/bin/env python3
"""把一次评测结果落盘，供 eval_baseline.py 消费。

为什么每个 suite 写一个分片，而不是共用一个 results.json：
多条测试并行跑时，"读-改-写"同一个文件会丢数据（后写的覆盖先写的），
且丢失是静默的。分片文件几乎不会撞名，汇总交给 eval_baseline.py 的目录模式
（目录模式会主动忽略 consolidate 产物，避免陈旧快照盖掉新分片）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

DEFAULT_DIR = os.environ.get("EVAL_RESULTS_DIR", "eval-results")


def _safe(name: str) -> str:
    """文件名只保留可移植字符；中文用 hash 兜底会丢可读性，所以保留中文、去掉路径符号。"""
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    return cleaned or "suite"


def _write(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # 先写临时文件再改名：避免进程被杀时留下半个 JSON，让基线对比读到坏数据
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def record(name: str, passed: int, total: int, failures: list[str] | None = None,
           out_dir: str | None = None) -> str:
    """写入一个**离线** suite 的分片；返回文件路径。"""
    d = out_dir or DEFAULT_DIR
    payload = {
        "suite": name,
        # kind 决定基线的严格度：offline 是纯函数、容忍度 0；
        # live 真打模型、有随机性、容忍度要 >0。混进同一份基线，退化判定失去意义。
        # 文件名前缀也能推出 kind，但 consolidate() 之后前缀信息会丢，
        # 所以记录里必须留这个字段。
        "kind": "offline",
        "passed": int(passed),
        "total": int(total),
        "rate": round(passed / total, 4) if total else 0.0,
        "failures": list(failures or []),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    return _write(os.path.join(d, f"offline-{_safe(name)}.json"), payload)


def record_live(name: str, passed: int, total: int, notes: list[str] | None = None,
                out_dir: str | None = None, kind: str = "live") -> str:
    """在线评测（真打模型）的结果落盘。

    与 record() 的差别：文件名用 live- 前缀、kind 按 live/live-strict 落，
    额外带 notes。

    kind 会被 eval_baseline.py 读走选严格度：
      live         容忍 1 条（模型随机性），可用 --allow-flip 覆盖
      live-strict  容忍 0 条（安全类：泄漏/PII/越权/编造——随机性不是豁免理由）
    注意别与另一件事混淆：基线报"不可判定（退出码 2）"的条件是
    **分母与基线不一致**，不是样本量小；小样本照常判定，只是在输出里
    标注"不足以支撑结论"，提醒你别把 1/1 当 100%。

    离线与在线可以放同一份 baseline（靠 kind 区分严格度），
    但评审时建议分开两份：容忍口径不同，混在一起很难看出哪条红是真的。
    分母 total 应传"真正被测到的条数"（跳过的不进分母），原因见 SKILL.md 陷阱四。
    """
    if kind not in ("live", "live-strict"):
        raise ValueError(f"record_live 的 kind 只能是 live/live-strict，收到 {kind!r}")
    d = out_dir or DEFAULT_DIR
    payload = {
        "suite": name,
        "kind": kind,
        "passed": int(passed),
        "total": int(total),
        "rate": round(passed / total, 4) if total else 0.0,
        "notes": list(notes or []),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    prefix = f"{kind}-" if kind == "live-strict" else "live-"
    return _write(os.path.join(d, f"{prefix}{_safe(name)}.json"), payload)


def consolidate(out_dir: str | None = None, target: str = "results.json") -> str:
    """把分片合并成一个文件（给不方便用目录模式的地方）。"""
    d = out_dir or DEFAULT_DIR
    merged: dict[str, dict] = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or fn == target:
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "suite" in data:
            merged[data["suite"]] = data
    return _write(os.path.join(d, target), {"suites": merged})


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    # 冒烟：造两个分片再合并，验证形状能被 eval_baseline.py 读懂
    tmp = os.path.join("_eval_smoke")
    record("smoke-A", 3, 3, out_dir=tmp)
    record("smoke-B", 2, 4, ["case-2 未通过"], out_dir=tmp)
    print("分片已写入:", tmp)
    print("合并结果:", consolidate(tmp))
    print("下一步: python eval_baseline.py --results " + tmp
          + " --baseline " + os.path.join(tmp, "base.json") + " --update")
    sys.exit(0)
