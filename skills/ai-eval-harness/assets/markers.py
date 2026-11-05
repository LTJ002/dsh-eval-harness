#!/usr/bin/env python3
"""判据词表：把"换业务必须改源码"的部分外置成配置。

为什么外置
----------
DEGRADED_MARKERS / REFUSAL_MARKERS / NEGATION_MARKERS / SUCCESS_CLAIM_MARKERS /
FAIL_STATUSES / CAUSE_RULES 原本硬编码在 eval_online.py / eval_governance.py 里。
换项目、换语言就得改判据源码——而技能正文自己要求"改任何脚本后必跑 selftest"。
外置后：换业务只改 JSON，不动判定逻辑；配置本身也有自检断言。

加载规则（确定性，不猜）：
1. 环境变量 EVAL_MARKERS 指向的 JSON 文件优先；
2. 否则取本目录下的 markers.default.json；
3. 缺字段或类型不对 → 报错并退出（不静默用默认值顶替，否则"配了没生效"查不到）；
4. 所有词表按原始顺序转成 tuple，保持与旧版硬编码一致的行为。

用法：
    python markers.py --show                 # 打印当前生效的词表（排查用）
    python markers.py --validate            # 校验配置并退出
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
DEFAULT_PATH = HERE / "markers.default.json"

# 必须存在的键 → 期望类型。缺一个就报错，避免"半套配置"静默生效。
REQUIRED = {
    "degradedMarkers": list,
    "refusalMarkers": list,
    "negationMarkers": list,
    "successClaimMarkers": list,
    "failStatuses": list,
    "unitTokens": list,
    "causeRules": list,
}


def load_markers(path: str | os.PathLike | None = None) -> dict:
    """加载词表。返回 {键: tuple 或 list}，与旧版硬编码形状一致。"""
    p = Path(path or os.environ.get("EVAL_MARKERS") or DEFAULT_PATH)
    if not p.exists():
        raise SystemExit(
            f"找不到词表配置：{p}\n"
            f"判据词表已外置（本轮改动）。请确保 markers.default.json 与\n"
            f"markers.py 在同一目录一起部署；或设置 EVAL_MARKERS 指向你的配置文件。\n"
            f"参考：assets/CROSS_LANGUAGE.md 与 assets/README.md 的部署说明。")
    with open(p, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"词表配置根必须是对象：{p}")

    out: dict = {}
    for key, expected in REQUIRED.items():
        value = data.get(key)
        if not isinstance(value, expected):
            raise SystemExit(f"词表配置 {p} 缺字段或类型不对：{key} 应为 {expected.__name__}")
        # 字符串列表：逐项校验，避免混入 dict 让 `m in text` 抛 TypeError
        if expected is list and key != "causeRules":
            if any(not isinstance(x, str) for x in value):
                raise SystemExit(f"词表配置 {p} 的 {key} 必须全是字符串")
        out[key] = tuple(value) if expected is list else value

    # causeRules: [[类别, [关键词...]], ...]，结构独立校验
    for rule in out["causeRules"]:
        if not (isinstance(rule, (list, tuple)) and len(rule) == 2
                and isinstance(rule[0], str) and isinstance(rule[1], (list, tuple))
                and all(isinstance(k, str) for k in rule[1])):
            raise SystemExit(f"词表配置 {p} 的 causeRules 项形状不对：{rule!r}")

    out["_source"] = str(p)
    return out


def validate_markers(data: dict) -> list[str]:
    """纯函数：返回违规清单（空 = 合规）。供 selftest 直接断言。

    同时接受 list 与 tuple：load_markers() 把列表转成 tuple 保持旧硬编码行为，
    校验器不能只认 list，否则"自己校验自己"必然失败。
    """
    bad: list[str] = []

    def is_listlike(v):
        return isinstance(v, (list, tuple))

    for key, expected in REQUIRED.items():
        if key not in data:
            bad.append(f"缺字段 {key}")
            continue
        value = data[key]
        if expected is list:
            if not is_listlike(value):
                bad.append(f"{key} 类型不对")
                continue
        elif not isinstance(value, expected):
            bad.append(f"{key} 类型不对")
            continue
        if expected is list and key != "causeRules" and any(not isinstance(x, str) for x in value):
            bad.append(f"{key} 含非字符串项")
        if expected is list and key != "causeRules" and not value:
            bad.append(f"{key} 为空（词表空了判据会静默失效）")
    return bad


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="判据词表")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    m = load_markers()
    if args.show:
        print(json.dumps({k: (list(v) if isinstance(v, tuple) else v)
                          for k, v in m.items() if k != "_source"},
                         ensure_ascii=False, indent=2))
        print(f"source: {m['_source']}")
    bad = validate_markers(m)
    if bad:
        for b in bad:
            print(f"[FAIL] {b}")
        sys.exit(1)
    print(f"[PASS] 词表合规（{m['_source']}），{len(REQUIRED)} 组")
