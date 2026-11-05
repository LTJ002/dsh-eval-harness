# 其他语言的落盘器（形状约定）

`eval_baseline.py` 只认一种很窄的 JSON 形状，任何语言写出它就能接入：

```json
{
  "suite": "PII 脱敏",
  "kind": "offline",
  "passed": 13,
  "total": 13,
  "rate": 1.0,
  "failures": ["g34 未挂门禁"],
  "at": "2026-11-06T03:00:00"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `suite` | 是 | 评测名，会被 `_safe()` 处理成分片文件名 |
| `kind` | 是 | `offline` / `live-strict` / `live`，决定基线严格度 |
| `passed` / `total` | 是 | 整数；`total` 只放"真正被测到的条数" |
| `rate` | 否 | 通过率，供人读；判定不靠它 |
| `failures` | 否 | 失败明细，红的时候不用翻完整日志 |
| `at` | 否 | ISO 时间戳 |

## 分片文件名

```
offline-<suite>.json        # kind=offline
live-<suite>.json           # kind=live
live-strict-<suite>.json    # kind=live-strict
```

前缀是 `eval_baseline.py::_infer_kind` 的兜底依据：外部手写的结果文件即使漏了
`kind`，也能按前缀推出严格度（默认 `offline`，**不会**悄悄放宽成 `live`）。

## 写入纪律（所有语言一样）

1. **每个 suite 一个分片**，不要共用一个 `results.json`——并发写会覆盖且静默丢数据
2. **先写临时文件再原子改名**（`rename` / `os.replace`），进程被杀不留半个 JSON
3. **坏分片不静默当成通过**：汇总时读不了的跳过，并在输出里留痕
4. **不要写 `results.json` / `*-results.json` 汇总文件**当分片——目录模式会主动忽略它们（防陈旧快照盖掉新分片）

## 汇总文件形状（给不方便用目录模式的调用方）

```json
{ "suites": { "PII 脱敏": { ...原分片对象... } } }
```

分片必须是**内嵌对象**，不是序列化成转义字符串；否则 Python 侧读到 `str`
而不是 `dict`，跨语言契约就断了（Java 版的 `RawJson` 就是为这个存在的）。

## 现成实现

| 语言 | 文件 | 状态 |
|---|---|---|
| Python | `eval_results.py` | 完整实现，进 selftest |
| Java 17 | `EvalResults.java` | 完整实现，进 `npm test` |
| Node >= 18 | `EvalResults.mjs` | 完整实现，进 `npm test`（含 Python 互读验证） |
| Go / Rust | — | **未提供实现**：按上面的形状写即可，本仓库没有编译器验证过，故不附代码以免误导 |

Go / Rust 的建议最小实现：标准库 `encoding/json` / `serde_json` 写 struct →
`os.WriteFile(tmp)` → `os.Rename(tmp, final)`，字段与上表一一对应。
写完后用 `python eval_baseline.py --results <dir> --baseline <base> --update`
验证一次形状能被读出来，再接 CI。
