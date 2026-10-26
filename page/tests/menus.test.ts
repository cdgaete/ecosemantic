import { menus, type MenuContext, type MenuItem } from '@/window/menus'

const nothing = (): void => undefined

function context(patch: Partial<MenuContext>): MenuContext {
  return { systemId: null, resultOpen: false, openRequests: 0, theme: 'ecosemantic', openNavigation: nothing, importFile: nothing, downloadResult: nothing, setPanelMode: nothing, panelMode: 'beside', setTheme: nothing, newRequest: nothing, reorganise: nothing, resetLayout: nothing, ...patch }
}

function seek(items: MenuItem[], key: string): MenuItem | null {
  for (const item of items) {
    if (item.key === key) return item
    const inside = item.items ? seek(item.items, key) : null
    if (inside) return inside
  }
  return null
}

function find(items: MenuItem[], key: string): MenuItem {
  const found = seek(items, key)
  if (found === null) throw new Error(`no menu item ${key}`)
  return found
}

const all = (patch: Partial<MenuContext>): MenuItem[] => menus(context(patch)).flatMap((menu) => menu.items)

describe('menus', () => {
  it('are File, Calculate, View and Requests', () => {
    expect(menus(context({})).map((menu) => menu.label)).toEqual(['File', 'Calculate', 'View', 'Requests'])
  })

  it('disable what acts on a system while none is on the canvas', () => {
    const items = all({})
    for (const key of ['export', 'import', 'impact', 'simulation', 'activity', 'details', 'new-request', 'open-requests']) expect(find(items, key).disabled).toBe(true)
    expect(find(items, 'open').disabled).toBeFalsy()
    expect(find(items, 'navigation').disabled).toBeFalsy()
  })

  it('offers reorganising the graph and resetting what was placed', () => {
    expect(find(all({ systemId: 's1' }), 'reorganise').disabled).toBeFalsy()
    expect(find(all({ systemId: 's1' }), 'reset-layout').disabled).toBeFalsy()
    expect(find(all({ systemId: null }), 'reset-layout').disabled).toBe(true)
  })

  it('name each export by its address, the tables before openLCA', () => {
    const exported = find(all({ systemId: 's1' }), 'export').items ?? []
    expect(exported.map((item) => item.label)).toEqual(['Tables (CSV + YAML)', 'openLCA package'])
    expect(exported[0].href).toContain('/api/product-systems/s1/tables.zip')
    expect(exported[1].href).toContain('/api/product-systems/s1/package.zip')
  })

  it('offer a result as files only while one is open', () => {
    expect(find(all({ systemId: 's1' }), 'download').disabled).toBe(true)
    expect(find(all({ systemId: 's1', resultOpen: true }), 'download').disabled).toBe(false)
  })

  it('open the list of product systems from File', () => {
    expect(find(all({}), 'all-systems').to).toBe('/')
    expect(find(all({}), 'all-systems').disabled).toBeFalsy()
  })

  it('open the calculation on the type the item names', () => {
    const items = all({ systemId: 's1' })
    expect(find(items, 'impact').to).toBe('/systems/s1/results/setup')
    expect(find(items, 'simulation').to).toBe('/systems/s1/results/setup?kind=simulation')
  })

  it('open the results on record from Calculate', () => {
    expect(find(all({ systemId: 's1' }), 'results').to).toBe('/systems/s1/results')
    expect(find(all({}), 'results').disabled).toBe(true)
  })

  it('offer the panel the two states it is not in', () => {
    const labels = (mode: 'beside' | 'expanded' | 'collapsed'): string[] =>
      (find(all({ systemId: 's1', panelMode: mode }), 'panel').items ?? []).filter((item) => !item.disabled).map((item) => item.label)
    expect(labels('beside')).toEqual(['Expand', 'Collapse'])
    expect(labels('expanded')).toEqual(['Beside the graph', 'Collapse'])
    expect(labels('collapsed')).toEqual(['Beside the graph', 'Expand'])
  })

  it('count the open requests', () => {
    expect(find(all({ systemId: 's1', openRequests: 2 }), 'open-requests').label).toBe('Open requests (2)')
  })
})
