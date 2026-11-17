import { pageTitle } from '@/window/pageTitle'

describe('pageTitle', () => {
  it.each([
    ['/', 'Product systems'],
    ['/databases', 'Databases'],
    ['/databases/ecoinvent-3.12-cutoff/datasets', 'ecoinvent-3.12-cutoff'],
    ['/databases/a%20b/flows', 'a b'],
    ['/nowhere', 'Not found'],
  ])('titles %s as %s', (pathname, title) => {
    expect(pageTitle(pathname)).toBe(title)
  })
})
