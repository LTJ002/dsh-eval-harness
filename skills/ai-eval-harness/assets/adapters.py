#!/usr/bin/env python3
"""评测适配器：把"请改这四处"的文字约定变成可插拔契约。

为什么
------
eval_online.py 原本把 login() / chat() / tool_calls_of() / tool_call_records()
写成模块级函数，接入项目要**改评测器源码**——与"换项目零改动判据引擎"矛盾。
这里提供一层薄注册：项目侧只需写一个模块、导出同名函数，设置
EVAL_ADAPTER=<模块文件路径> 即可，判据、分母纪律、落盘全部不动。

内置 base 适配器 = 原来的 HTTP/SSE 实现（默认，100% 向后兼容）。
任何未提供的函数都回退到 base，不强制项目实现全套。

接口（全部可选实现）：
    login() -> str                                   # 返回 token
    new_session(token) -> str                        # 返回会话 id
    chat(token, session_id, question) -> (text, cost_s)
    tool_calls_of(conversation_id) -> list[str] | None
    tool_call_records(conversation_id) -> list[dict] | None

三态纪律不由适配器决定：None = 观测不到（不判失败）的语义在判据侧，
适配器只负责"能不能拿到数据"。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_BASE = None  # 延迟绑定，避免循环 import


def _load_base():
    global _BASE
    if _BASE is None:
        import eval_online as _eo  # noqa: PLC0415
        _BASE = _eo
    return _BASE


def load_adapter(module_path: str | None = None):
    """从文件路径加载适配器模块。返回模块对象；未配置时返回 base 模块。

    加载失败（路径不存在/语法错/导入异常）直接抛错，不静默回退——
    "配了适配器却没生效"是最难查的一类假绿。
    """
    path = module_path or os.environ.get("EVAL_ADAPTER")
    if not path:
        return _load_base()
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到适配器：{p}（EVAL_ADAPTER 指向的文件不存在）")
    spec = importlib.util.spec_from_file_location("eval_adapter_user", p)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载适配器：{p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_adapter_user"] = mod
    spec.loader.exec_module(mod)
    return mod


def resolve(adapter, name: str):
    """取适配器的函数；没实现就回退 base。纯函数，可断言。"""
    fn = getattr(adapter, name, None)
    if callable(fn):
        return fn
    return getattr(_load_base(), name)


def adapter_info(adapter) -> dict:
    """报告哪些函数来自适配器、哪些回退 base（排查"配了没生效"用）。"""
    names = ("login", "new_session", "chat", "tool_calls_of", "tool_call_records")
    out = {}
    for n in names:
        fn = getattr(adapter, n, None)
        out[n] = "adapter" if callable(fn) else "base"
    return out
