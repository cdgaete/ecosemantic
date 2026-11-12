/// <reference types="node" />
import { readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'

const here = path.dirname(url.fileURLToPath(import.meta.url))
const css = readFileSync(path.resolve(here, '../src/styles/index.css'), 'utf8')

const SELECTORS = [
  ':root,\n[data-theme="cobalt"]',
  '[data-theme="ecosemantic"]',
  '[data-theme="openlca"]',
]

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

it('defines the three themes in the order cobalt, ecosemantic, openlca', () => {
  expect(blocks.map((block) => block.selector)).toEqual(SELECTORS)
})

it('gives the three themes the same token names in the same order', () => {
  const [cobalt, ecosemantic, openlca] = blocks.map((block) => block.names)
  expect(ecosemantic).toEqual(cobalt)
  expect(openlca).toEqual(cobalt)
  expect(cobalt).toHaveLength(53)
  expect(cobalt.slice(-2)).toEqual(['--font-sans', '--font-mono'])
})

it('ties the dark variant to the ecosemantic theme rather than the operating system', () => {
  expect(css.split('\n')).toContain(
    '@custom-variant dark (&:where([data-theme="ecosemantic"], [data-theme="ecosemantic"] *));',
  )
})
