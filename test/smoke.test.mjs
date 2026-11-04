import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseYaml } from 'yaml'

const root = dirname(dirname(fileURLToPath(import.meta.url)))

// index.js 以 provider 形式挂到 ctx.skills 上，直接 import 会触发 apply 前的
// 模块级代码；这里不 mock 宿主，只验证「技能包能被解析出来」这一层契约——
// 与 index.js 的 parseSkill 保持相同的最小语义。
function parseFrontmatter(raw) {
  const firstLineEnd = raw.indexOf('\n')
  if (firstLineEnd < 0) return undefined
  if (raw.slice(0, firstLineEnd).replace(/\r$/, '') !== '---') return undefined
  const closing = raw.indexOf('\n---', firstLineEnd + 1)
  if (closing < 0) return undefined
  const parsed = parseYaml(raw.slice(firstLineEnd + 1, closing))
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return undefined
  return parsed
}

test('skills 目录至少包含一个技能', () => {
  const entries = readdirSync(join(root, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
  assert.ok(entries.length >= 1, 'skills/ 下没有任何技能目录')
})

test('SKILL.md frontmatter 合法且 name 符合命名规则', () => {
  const entries = readdirSync(join(root, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
  for (const entry of entries) {
    const raw = readFileSync(join(root, 'skills', entry.name, 'SKILL.md'), 'utf8')
    const meta = parseFrontmatter(raw)
    assert.ok(meta, `${entry.name}/SKILL.md 缺少合法 frontmatter`)
    assert.match(meta.name, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, `技能名非法: ${meta.name}`)
    assert.ok(typeof meta.description === 'string' && meta.description.length > 0,
      `${meta.name} 缺少 description`)
  }
})

test('每个技能至少带一个可运行资产且 selftest 存在', () => {
  const entries = readdirSync(join(root, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
  for (const entry of entries) {
    const files = readdirSync(join(root, 'skills', entry.name, 'assets'))
    assert.ok(files.includes('selftest.py'), `${entry.name} 缺少 assets/selftest.py（门禁的一部分）`)
    assert.ok(files.includes('mutation_check.py'), `${entry.name} 缺少 assets/mutation_check.py（门禁的一部分）`)
  }
})

test('package.json 声明 dsh.bundle 且 patch 文件存在', () => {
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
  assert.equal(pkg.dsh?.bundle?.patch, './cordis.patch.yml')
  // patch 文档根是列表（- insert: ...），与生态样板的 cordis.patch.yml 形态一致
  const doc = parseYaml(readFileSync(join(root, 'cordis.patch.yml'), 'utf8'))
  const patch = Array.isArray(doc) ? doc[0] : doc
  assert.ok(patch?.insert, 'cordis.patch.yml 缺少 insert 段')
  assert.equal(patch.insert[0].name, 'dsh-eval-harness')
})
