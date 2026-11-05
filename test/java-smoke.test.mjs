import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const assets = join(dirname(fileURLToPath(import.meta.url)),
  '..', 'skills', 'ai-eval-harness', 'assets')

// Java 侧落盘器的编译 + 运行冒烟：验证「产出的 JSON 形状与 Python 版一致」。
// 之前这块一直只是 README 里的"已知边界"，现在固化进 npm test。
// 没有 JDK 的环境跳过（java/javac 不可用时不是失败——但会在输出里显式说明，
// 不静默假装测过）。与 SKILL.md 的"没测到 ≠ 通过"同一纪律。
function hasJdk() {
  try {
    execFileSync('javac', ['-version'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

test('EvalResults.java 编译并产出与 Python 同形的 JSON', { skip: !hasJdk() && 'JDK 不可用' }, (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-java-smoke-'))
  try {
    mkdirSync(join(dir, 'eval'))
    const javaSrc = readFileSync(join(assets, 'EvalResults.java'), 'utf8')
    writeFileSync(join(dir, 'eval', 'EvalResults.java'), javaSrc)
    writeFileSync(join(dir, 'Smoke.java'),
      'import eval.EvalResults; import java.util.List;\n' +
      'public class Smoke { public static void main(String[] a) {\n' +
      '  EvalResults.record("smoke-suite", 3, 4, List.of("c2 failed"));\n' +
      '  System.out.println(EvalResults.consolidate());\n' +
      '} }\n')

    execFileSync('javac', ['-encoding', 'UTF-8', 'eval/EvalResults.java', 'Smoke.java'],
      { cwd: dir, stdio: 'pipe' })
    const outDir = join(dir, 'out')
    execFileSync('java', [`-Deval.results.dir=${outDir}`, 'Smoke'],
      { cwd: dir, stdio: 'pipe' })

    const shard = JSON.parse(readFileSync(join(outDir, 'offline-smoke-suite.json'), 'utf8'))
    assert.equal(shard.suite, 'smoke-suite')
    assert.equal(shard.passed, 3)
    assert.equal(shard.total, 4)
    assert.equal(shard.rate, 0.75)
    // kind 必须与 Python 版 record() 一致，不能靠文件名前缀隐式兜底
    assert.equal(shard.kind, 'offline', 'Java 分片缺 kind 会让基线靠文件名猜严格度')
    assert.deepEqual(shard.failures, ['c2 failed'])

    // 汇总文件必须是 {"suites": {name: <对象>}}，分片要内嵌成对象而不是转义字符串
    const merged = JSON.parse(readFileSync(join(outDir, 'results.json'), 'utf8'))
    assert.equal(typeof merged.suites['smoke-suite'], 'object',
      '汇总里的分片被序列化成字符串了（跨语言读取会断）')
    assert.equal(merged.suites['smoke-suite'].passed, 3)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})
