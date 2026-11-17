/// <reference types="node" />
import { readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'

const here = path.dirname(url.fileURLToPath(import.meta.url))
const css = readFileSync(path.resolve(here, '../src/styles/index.css'), 'utf8')

const SELECTORS = [':root,\n[data-theme="light"]', '[data-theme="dark"]']

interface Block {
  selector: string
  names: string[]
}

function themeBlocks(source: string): Block[] {
  const blocks: Block[] = []
  for (const match of source.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const preamble = match[1]
    const selector = preamble
      .slice(Math.max(preamble.lastIndexOf(';'), preamble.lastIndexOf('}')) + 1)
      .trim()
    if (!/^(?::root,\s*)?\[data-theme="[a-z]+"\]$/.test(selector)) continue
    const names = Array.from(match[2].matchAll(/^\s*(--[\w-]+|color-scheme)\s*:/gm), (d) => d[1])
    blocks.push({ selector, names })
  }
  return blocks
}

const blocks = themeBlocks(css)

it('defines two themes, light then dark', () => {
  expect(blocks.map((block) => block.selector)).toEqual(SELECTORS)
})

it('gives the two themes the same token names in the same order, and no typeface', () => {
  const [light, dark] = blocks.map((block) => block.names)
  expect(dark).toEqual(light)
  expect(light).toHaveLength(51)
  expect(light.filter((name) => name.startsWith('--font'))).toEqual([])
})

it("draws both themes in Tailwind's default system stacks, declaring no typeface and loading no font file", () => {
  expect(css).not.toMatch(/--font-(sans|mono)\s*:/)
  expect(css).not.toContain('@font-face')
  const defaults = readFileSync(path.resolve(here, '../node_modules/tailwindcss/theme.css'), 'utf8')
  expect(defaults).toMatch(/--font-sans:\s*-apple-system, BlinkMacSystemFont, 'Segoe UI'/)
})

it('ties the dark variant to the dark theme rather than the operating system', () => {
  expect(css.split('\n')).toContain('@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));')
})
