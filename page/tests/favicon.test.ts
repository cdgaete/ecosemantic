import index from '../index.html?raw'

it('links the logo as the favicon of the page', () => {
  expect(index).toContain('rel="icon"')
  expect(index).toContain('type="image/svg+xml"')
  expect(index).toContain('href="/src/assets/logo.svg"')
})
