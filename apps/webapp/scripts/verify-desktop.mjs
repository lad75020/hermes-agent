import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(root, '../..')
const baseline = path.join(root, '.scratch/desktop-before.json')
const files = execFileSync('git', ['ls-files', '-co', '--exclude-standard', '-z', 'apps/desktop'], { cwd: repo }).toString().split('\0').filter(Boolean)
const hashes = Object.fromEntries(await Promise.all(files.map(async file => [file, createHash('sha256').update(await fs.readFile(path.join(repo, file))).digest('hex')])))
if (process.argv.includes('--record')) {
  await fs.mkdir(path.dirname(baseline), { recursive: true })
  // An existing baseline must not be silently replaced.
  await fs.writeFile(baseline, JSON.stringify(hashes, null, 2), { flag: 'wx' })
  console.log(`Recorded ${files.length} tracked/non-ignored Desktop files`)
} else {
  const before = JSON.parse(await fs.readFile(baseline, 'utf8'))
  const changed = [...new Set([...Object.keys(before), ...files])].filter(file => before[file] !== hashes[file])
  if (changed.length) throw new Error(`Desktop tree changed:\n${changed.join('\n')}`)
  const diff = execFileSync('git', ['diff', '--', 'apps/desktop'], { cwd: repo }).toString()
  if (diff) throw new Error('Desktop has a tracked diff')
  console.log(`PASS: ${files.length} Desktop SHA-256 fingerprints unchanged; tracked diff empty; untracked inventory unchanged`)
}
