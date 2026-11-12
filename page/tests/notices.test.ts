/// <reference types="node" />
import { readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'
import { describe, expect, it } from 'vitest'
import { fontNotices, render } from '../scripts/render-notices.ts'

const here = path.dirname(url.fileURLToPath(import.meta.url))
const fonts = path.resolve(here, '../src/assets/fonts')

function licence(name: string): string {
  return readFileSync(path.join(fonts, name), 'utf8')
}

describe('the third-party notices', () => {
  it('lists each package by name and version with its licence and its text', () => {
    const text = render([
      { name: 'zustand', version: '5.0.2', license: 'MIT', homepage: 'https://zustand.example', texts: ['MIT zustand'] },
      { name: '@radix-ui/react-tabs', version: '1.1.13', license: 'MIT', homepage: undefined, texts: ['MIT radix'] },
    ])
    expect(text.indexOf('@radix-ui/react-tabs 1.1.13')).toBeLessThan(text.indexOf('zustand 5.0.2'))
    expect(text).toContain('zustand 5.0.2 (MIT)\nhttps://zustand.example\n\nMIT zustand')
    expect(text).toContain('@radix-ui/react-tabs 1.1.13 (MIT)\n\nMIT radix')
  })

  it('gives each bundled font its own name, version and OFL text', () => {
    expect(fontNotices(fonts)).toEqual([
      {
        name: 'Source Sans 3',
        version: '3.052',
        license: 'OFL-1.1',
        homepage: undefined,
        texts: [licence('OFL-SourceSans3.txt')],
      },
      {
        name: 'JetBrains Mono',
        version: '2.211',
        license: 'OFL-1.1',
        homepage: undefined,
        texts: [licence('OFL-JetBrainsMono.txt')],
      },
    ])
  })

  it('renders both fonts under their versions and both OFL texts', () => {
    const text = render(fontNotices(fonts))
    expect(text).toContain('Source Sans 3 3.052 (OFL-1.1)')
    expect(text).toContain('JetBrains Mono 2.211 (OFL-1.1)')
    expect(text.match(/SIL OPEN FONT LICENSE/g)).toHaveLength(2)
  })

  it('says when a package carries no licence file', () => {
    const text = render([{ name: 'clsx', version: '2.1.1', license: 'MIT', homepage: undefined, texts: [] }])
    expect(text).toContain('clsx 2.1.1 (MIT)\n\nThe package carries no licence file; its package.json names MIT.')
  })
})
