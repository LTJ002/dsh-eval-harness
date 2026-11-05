import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pathToFileURL } from 'node:url'

const assets = join(dirname(fileURLToPath(import.meta.url)),
  '..', 'skills', 'ai-eval-harness', 'assets')

test('EvalResults.mjs 产出与 Python 同形的分片，且 kind 字段齐全', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-node-shard-'))
  try {
    const mod = await import(pathToFileURL(join(assets, 'EvalResults.mjs')).href)
    const p = mod.record('node-suite', 3, 4, ['c2 failed'], 'offline', dir)
    const shard = JSON.parse(readFileSync(p, 'utf8'))
    assert.equal(shard.suite, 'node-suite')
    assert.equal(shard.kind, 'offline')
    assert.equal(shard.passed, 3)
    assert.equal(shard.total, 4)
    assert.equal(shard.rate, 0.75)
    assert.deepEqual(shard.failures, ['c2 failed'])

    // live-strict 与 live 前缀也要正确
    const p2 = mod.record('strict-suite', 5, 5, [], 'live-strict', dir)
    assert.match(p2, /live-strict-strict-suite\.json$/)
    const p3 = mod.record('live-suite', 4, 5, [], 'live', dir)
    assert.match(p3, /live-live-suite\.json$/)
    assert.throws(() => mod.record('x', 1, 1, [], 'bogus', dir), /kind/)

    // 汇总文件必须内嵌对象而不是转义字符串
    mod.consolidate(dir)
    const merged = JSON.parse(readFileSync(join(dir, 'results.json'), 'utf8'))
    assert.equal(typeof merged.suites['node-suite'], 'object')
    assert.equal(merged.suites['node-suite'].passed, 3)

    // Python 侧能直接读（跨语言契约）
    const out = execFileSync('python', ['-c',
      'import sys, json, eval_baseline as B; '
      + 's=B.load_results(sys.argv[1]); '
      + 'print(json.dumps({k: [v["kind"], v["passed"], v["total"]] for k, v in s.items()}))',
      dir], { cwd: assets, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } })
    const parsed = JSON.parse(out)
    assert.deepEqual(parsed['node-suite'], ['offline', 3, 4])
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})
