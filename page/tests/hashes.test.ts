/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'
import { movedSince } from '@/lib/hashes'

const here = path.dirname(url.fileURLToPath(import.meta.url))
const sources = path.resolve(here, '../src')
const HASHES = new Set(['at_hash', 'hash_now', 'hash', 'current', 'recordedOn'])
const OPERAND = String.raw`(?:[A-Za-z_$][\w$.]*|'[^']*'|"[^"]*")`
const COMPARISON = new RegExp(String.raw`(${OPERAND})\s*(?:===|!==)\s*(${OPERAND})`, 'g')

const VALUES: (string | null | undefined)[] = [null, undefined, '', 'a', 'b']

function hashName(operand: string): boolean {
  return HASHES.has(operand.slice(operand.lastIndexOf('.') + 1))
}

function comparesHashes(line: string): boolean {
  for (const [, left, right] of line.matchAll(COMPARISON)) {
    if (hashName(left) && hashName(right)) return true
  }
  return false
}

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return files(full)
    return /\.tsx?$/.test(entry.name) ? [full] : []
  })
}

describe('movedSince', () => {
  it('answers true only for two known hashes that differ', () => {
    const moved = VALUES.flatMap((at) => VALUES.filter((now) => movedSince(at, now)).map((now) => `${String(at)} → ${String(now)}`))
    expect(moved).toEqual(['a → b', 'b → a'])
  })
})

describe('the page answers "moved since" in one place', () => {
  it('reads two hashes compared as a second answer, and a hash compared with an unknown as not one', () => {
    expect(comparesHashes('const earlier = call.at_hash !== null && call.at_hash !== current')).toBe(true)
    expect(comparesHashes("const stale = current !== '' && hash !== '' && current !== hash")).toBe(true)
    expect(comparesHashes('const moved = system !== undefined && system.hash !== null && system.hash !== run.at_hash')).toBe(true)
    expect(comparesHashes('{view.system.hash === null ? (')).toBe(false)
    expect(comparesHashes("if (hash === '' && current !== '') setHash(current)")).toBe(false)
    expect(comparesHashes('const first = fittedFor.current !== system.id')).toBe(false)
  })

  it('compares no two hashes outside lib/hashes.ts', () => {
    const offenders = files(sources)
      .filter((file) => path.relative(sources, file) !== path.join('lib', 'hashes.ts'))
      .flatMap((file) =>
        readFileSync(file, 'utf8')
          .split('\n')
          .flatMap((line, at) => (comparesHashes(line) ? [`${path.relative(sources, file)}:${at + 1}: ${line.trim()}`] : [])),
      )
    expect(offenders).toEqual([])
  })
})
