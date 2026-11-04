#!/usr/bin/env python3
"""评测运行清单生成器：回答"这次评测为什么和上次不一样"。

每次评测前后各跑一次，落 eval-run-manifest.json：
- runId / 生成时间
- gitCommit（git 不可用时如实记 "unknown"，不猜）
- prompts   {相对路径: sha256}   --prompts-dir 下所有 .md
- datasets  {相对路径: sha256}   --dataset-dir 下所有 .jsonl
- config    --set key=value 原样记录（chunkSize / topK / temperature / 模型名…）

纪律：
- **密钥、个人数据不进清单**。--set 只放非敏感运行参数；
  证书、token、用户标识一概不要写——可复现不等于把敏感信息写进结果文件。
- 对比两份 manifest 的差异 = 找出结果变化的候选原因：
  提示词哈希变了、数据集变了、config 变了、git commit 变了。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _sha256_of(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _hash_dir(root: str, suffix: str) -> dict[str, str]:
    """root 下指定后缀文件的 {相对路径: sha256}，按名字排序保证稳定。"""
    out: dict[str, str] = {}
    if not root or not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if not name.endswith(suffix):
            continue
        full = os.path.join(root, name)
        if os.path.isfile(full):
            out[name] = _sha256_of(full)
    return out


def git_commit(cwd: str | None = None) -> str:
    """当前提交短哈希；不在 git 仓库里就如实返回 unknown。"""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        ).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def build_manifest(prompts_dir: str, dataset_dir: str,
                   extra_config: dict[str, str] | None = None,
                   commit: str | None = None) -> dict:
    """清单本体。抽成纯函数是为了 selftest 能断言哈希正确、且能发现文件变更。"""
    return {
        "runId": f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "gitCommit": commit if commit is not None else git_commit(),
        "prompts": _hash_dir(prompts_dir, ".md"),
        "datasets": _hash_dir(dataset_dir, ".jsonl"),
        "config": dict(extra_config or {}),
    }


def manifest_diff(a: dict, b: dict) -> list[str]:
    """两份清单的可读差异。空列表 = 没有可解释的变化。"""
    diffs: list[str] = []
    for key in ("gitCommit",):
        if a.get(key) != b.get(key):
            diffs.append(f"{key}: {a.get(key)} → {b.get(key)}")
    for section in ("prompts", "datasets"):
        ha, hb = a.get(section) or {}, b.get(section) or {}
        for name in sorted(set(ha) | set(hb)):
            if ha.get(name) != hb.get(name):
                if name not in ha:
                    diffs.append(f"{section}/{name}: 新增")
                elif name not in hb:
                    diffs.append(f"{section}/{name}: 移除")
                else:
                    diffs.append(f"{section}/{name}: 内容变化")
    ca, cb = a.get("config") or {}, b.get("config") or {}
    for key in sorted(set(ca) | set(cb)):
        if ca.get(key) != cb.get(key):
            diffs.append(f"config/{key}: {ca.get(key)} → {cb.get(key)}")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description="生成评测运行清单")
    ap.add_argument("--prompts-dir", default="eval",
                    help="提示词 .md 所在目录（递归一层）")
    ap.add_argument("--dataset-dir", default="eval/datasets",
                    help="数据集 .jsonl 所在目录")
    ap.add_argument("--set", dest="cfg", action="append", default=[],
                    help="运行参数，key=value，可多次；不要放密钥/PII")
    ap.add_argument("--out", default="eval/run-manifest.json")
    args = ap.parse_args()

    extra: dict[str, str] = {}
    for item in args.cfg:
        if "=" not in item:
            print(f"[ERROR] --set 需要 key=value 形式，收到 {item!r}")
            return 2
        k, v = item.split("=", 1)
        extra[k] = v

    manifest = build_manifest(args.prompts_dir, args.dataset_dir, extra)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    n_prompts = len(manifest["prompts"])
    n_datasets = len(manifest["datasets"])
    print(f"清单已写入: {args.out}")
    print(f"  gitCommit={manifest['gitCommit']}  prompts={n_prompts} 个  "
          f"datasets={n_datasets} 个  config={len(manifest['config'])} 项")
    if os.path.exists(args.out) and n_prompts == 0 and n_datasets == 0:
        print("[WARN] 没有指纹到任何 .md/.jsonl——目录传对了吗？")
    return 0


if __name__ == "__main__":
    sys.exit(main())
