// Node.js 结果落盘器：产出的 JSON 形状与 assets/eval_results.py 完全一致。
// 零依赖，Node >= 18（node:fs / node:path / node:url）。
//
// 用法：
//   import { record, consolidate } from './EvalResults.mjs'
//   record('PII 脱敏', 13, 13, ['g34 未挂门禁'])
//
// 为什么每个 suite 一个分片：多测试并行写同一个 results.json 会静默丢数据。
// 分片名前缀 offline-/live-/live-strict- 与 Python 侧 _infer_kind 的兜底一致。

import { writeFileSync, readdirSync, readFileSync, mkdirSync, renameSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const DEFAULT_DIR = process.env.EVAL_RESULTS_DIR || 'eval-results'

function safe (name) {
  const cleaned = String(name).replace(/[\\/:*?"<>|\s]+/g, '_').replace(/^_+|_+$/g, '')
  return cleaned || 'suite'
}

function writeAtomic (path, payload) {
  mkdirSync(dirname(path), { recursive: true })
  const tmp = path + '.tmp'
  writeFileSync(tmp, JSON.stringify(payload, null, 2) + '\n', 'utf8')
  renameSync(tmp, path)
  return path
}

/** 记录一个 suite 的结果。kind 决定基线的严格度（offline 0 / live-strict 0 / live 1）。 */
export function record (suite, passed, total, failures = [], kind = 'offline', outDir = DEFAULT_DIR) {
  if (!['offline', 'live', 'live-strict'].includes(kind)) {
    throw new Error(`record: kind 只能是 offline/live/live-strict，收到 ${kind}`)
  }
  const payload = {
    suite: String(suite),
    kind,
    passed: Number(passed),
    total: Number(total),
    rate: total ? Math.round((passed / total) * 10000) / 10000 : 0,
    failures: Array.isArray(failures) ? failures.map(String) : [],
    at: new Date().toISOString()
  }
  const prefix = kind === 'offline' ? 'offline-' : kind === 'live-strict' ? 'live-strict-' : 'live-'
  return writeAtomic(join(outDir, `${prefix}${safe(suite)}.json`), payload)
}

/** 汇总分片为 {"suites": {...}}，内嵌原对象（不是转义字符串）。 */
export function consolidate (outDir = DEFAULT_DIR) {
  const suites = {}
  for (const name of readdirSync(outDir).sort()) {
    if (!name.endsWith('.json') || name === 'results.json' || name.endsWith('-results.json')) continue
    try {
      const data = JSON.parse(readFileSync(join(outDir, name), 'utf8'))
      if (data && data.suite) suites[data.suite] = data
    } catch { /* 坏分片跳过，不静默当成通过 */ }
  }
  return writeAtomic(join(outDir, 'results.json'), { suites })
}

export const name = 'EvalResults'
