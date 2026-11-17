import { paths } from '@/lib/paths'

describe('paths', () => {
  it('addresses a database’s explorer and each of its sections', () => {
    expect(paths.explorer('fixture')).toBe('/databases/fixture/datasets')
    expect(paths.explorer('fixture', 'flows')).toBe('/databases/fixture/flows')
    expect(paths.explorer('fixture', 'methods', '?node=gwp')).toBe('/databases/fixture/methods?node=gwp')
  })

  it('addresses one flow and one indicator of a database', () => {
    expect(paths.flow('fixture', 'f1')).toBe('/databases/fixture/flows/f1')
    expect(paths.indicator('fixture', 'm_bff077f3bd')).toBe('/databases/fixture/methods/m_bff077f3bd')
  })

  it('addresses a background process of a database', () => {
    expect(paths.background('fixture', 'p1')).toBe('/databases/fixture/processes/p1')
  })
})
