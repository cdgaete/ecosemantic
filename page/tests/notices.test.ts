import { describe, expect, it } from 'vitest'
import { render } from '../scripts/render-notices.ts'

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

  it('says when a package carries no licence file', () => {
    const text = render([{ name: 'clsx', version: '2.1.1', license: 'MIT', homepage: undefined, texts: [] }])
    expect(text).toContain('clsx 2.1.1 (MIT)\n\nThe package carries no licence file; its package.json names MIT.')
  })
})
