import { useUi, type EditorTab } from '@/store/ui'

const tab = (id: string, path = `/systems/1/processes/${id}/general`): EditorTab => ({ id, kind: 'process', title: id, path })

describe('ui store', () => {
  beforeEach(() => {
    useUi.setState({ theme: 'dark', pinned: [], details: null, lastDetails: null, collapsed: {} })
  })

  it('remembers what Details showed last', () => {
    useUi.getState().showDetails(tab('a'))
    useUi.getState().showDetails(tab('a'))
    expect(useUi.getState().details?.id).toBe('a')
    useUi.getState().showDetails(tab('b'))
    expect(useUi.getState().details?.id).toBe('b')
    useUi.getState().showActivity()
    expect(useUi.getState().details).toBeNull()
    expect(useUi.getState().lastDetails?.id).toBe('b')
  })

  it('leaves the inspector as it is when Details shows a thing', () => {
    useUi.setState({ inspector: 'closed', sheetOpen: false })
    useUi.getState().showDetails(tab('a'))
    expect(useUi.getState().inspector).toBe('closed')
    expect(useUi.getState().sheetOpen).toBe(false)
  })

  it.each([
    ['beside', 'open'],
    ['expanded', 'widened'],
    ['collapsed', 'closed'],
    [undefined, 'open'],
  ])('opens a state saved at version 4 with panel %s as inspector %s', async (panelMode, inspector) => {
    const pinned = [tab('p')]
    localStorage.setItem(
      'ecosemantic-page',
      JSON.stringify({
        state: { theme: 'dark', panelWidth: 640, panelMode, navDocked: true, navWidth: 300, pinned, minimapOpen: false },
        version: 4,
      }),
    )
    await useUi.persist.rehydrate()
    const state = useUi.getState()
    expect(state.inspector).toBe(inspector)
    expect(state.theme).toBe('dark')
    expect(state.pinned).toEqual(pinned)
    expect(state.minimapOpen).toBe(false)
    expect('panelWidth' in state).toBe(false)
    expect('panelMode' in state).toBe(false)
    expect('navDocked' in state).toBe(false)
    expect('navWidth' in state).toBe(false)
    localStorage.removeItem('ecosemantic-page')
  })

  it('pins what Details holds once, keeps its page, and unpins it', () => {
    useUi.getState().showDetails(tab('a'))
    useUi.getState().pin()
    useUi.getState().pin()
    expect(useUi.getState().pinned.map((t) => t.id)).toEqual(['a'])
    useUi.getState().showDetails(tab('a', '/systems/1/processes/a/exchanges'))
    expect(useUi.getState().pinned[0].path).toBe('/systems/1/processes/a/exchanges')
    useUi.getState().unpin('a')
    expect(useUi.getState().pinned).toEqual([])
  })

  it('keeps no token in what it holds', () => {
    useUi.getState().showDetails(tab('a', '/systems/1/processes/a/general?token=secret'))
    expect(useUi.getState().details?.path).toBe('/systems/1/processes/a/general')
  })

  it.each(['light', 'dark'] as const)('stamps the %s theme on the document', (theme) => {
    useUi.getState().setTheme(theme)
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
  })

  it('opens on the light theme in a browser that has not chosen a theme', () => {
    expect(useUi.getInitialState().theme).toBe('light')
  })

  it('opens a state saved at version 0 in the light theme and keeps every other saved field', async () => {
    const pinned = [tab('p')]
    localStorage.setItem(
      'ecosemantic-page',
      JSON.stringify({
        state: {
          theme: 'ecosemantic',
          person: 'carlos',
          pinned,
          seen: { s1: 7 },
          collapsed: { general: true },
          formulaValues: true,
          minimapOpen: true,
        },
        version: 0,
      }),
    )
    await useUi.persist.rehydrate()
    expect(useUi.getState().theme).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(useUi.getState().person).toBe('carlos')
    expect(useUi.getState().pinned).toEqual(pinned)
    expect(useUi.getState().seen).toEqual({ s1: 7 })
    expect(useUi.getState().collapsed).toEqual({ general: true })
    expect(useUi.getState().formulaValues).toBe(true)
    expect(useUi.getState().minimapOpen).toBe(true)
    localStorage.removeItem('ecosemantic-page')
  })

  it.each([
    ['cobalt', 'light'],
    ['ecosemantic', 'dark'],
    ['openlca', 'light'],
  ])('opens a theme saved at version 1 as %s in the %s theme and keeps every other saved field', async (saved, theme) => {
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: saved, person: 'carlos' }, version: 1 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().theme).toBe(theme)
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
    expect(useUi.getState().person).toBe('carlos')
    localStorage.removeItem('ecosemantic-page')
  })

  it('opens a pinned tab of a page the explorer replaces on its explorer', async () => {
    const pinned = [
      { id: 'search:fixture:processes', kind: 'search', title: 'Processes · fixture', path: '/databases/fixture/search/processes' },
      { id: 'background:fixture:p1', kind: 'background', title: 'p1', path: '/databases/fixture/processes/p1' },
      { id: 'system:s1', kind: 'system', title: 's1', path: '/systems/s1' },
    ]
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { pinned }, version: 3 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().pinned.map((entry) => entry.kind)).toEqual(['explorer', 'explorer', 'system'])
    expect(useUi.getState().pinned.map((entry) => entry.path)).toEqual([
      '/databases/fixture/search/processes',
      '/databases/fixture/processes/p1',
      '/systems/s1',
    ])
    localStorage.removeItem('ecosemantic-page')
  })

  it('keeps a theme saved at version 2', async () => {
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: 'dark' }, version: 2 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().theme).toBe('dark')
    localStorage.removeItem('ecosemantic-page')
  })

  it('toggles a section', () => {
    useUi.getState().toggleSection('general')
    expect(useUi.getState().collapsed.general).toBe(true)
  })

  it('persists the fold of the build timeline and the width the inspector was dragged to', async () => {
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: 'dark' }, version: 5 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().timelineOpen).toBe(true)
    expect(useUi.getState().inspectorWidth).toBeNull()
    useUi.getState().setTimelineOpen(false)
    useUi.getState().setInspectorWidth(612)
    const saved = JSON.parse(localStorage.getItem('ecosemantic-page') ?? '{}') as { state: { timelineOpen: boolean; inspectorWidth: number | null } }
    expect(saved.state.timelineOpen).toBe(false)
    expect(saved.state.inspectorWidth).toBe(612)
    useUi.setState({ timelineOpen: true, inspectorWidth: null })
    localStorage.removeItem('ecosemantic-page')
  })

  it('persists the place the canvas tools were dropped at', async () => {
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: 'dark' }, version: 5 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().toolsOffset).toBeNull()
    useUi.getState().setToolsOffset({ x: -120, y: 340 })
    const saved = JSON.parse(localStorage.getItem('ecosemantic-page') ?? '{}') as { state: { toolsOffset: { x: number; y: number } | null } }
    expect(saved.state.toolsOffset).toEqual({ x: -120, y: 340 })
    useUi.setState({ toolsOffset: null })
    localStorage.removeItem('ecosemantic-page')
  })

  it('persists the databases a person folded and opened', async () => {
    useUi.setState({ navDatabases: {} })
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: 'dark' }, version: 5 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().navDatabases).toEqual({})
    useUi.getState().toggleNavDatabase('fixture')
    expect(useUi.getState().navDatabases).toEqual({ fixture: true })
    const saved = JSON.parse(localStorage.getItem('ecosemantic-page') ?? '{}') as { state: { navDatabases: Record<string, boolean> } }
    expect(saved.state.navDatabases).toEqual({ fixture: true })
    localStorage.removeItem('ecosemantic-page')
  })

  it('the chosen categories are persisted', async () => {
    useUi.setState({ resultCategories: {} })
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { theme: 'dark' }, version: 5 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().resultCategories).toEqual({})
    useUi.getState().setResultCategory('s1', 'm_gwp')
    expect(useUi.getState().resultCategories).toEqual({ s1: 'm_gwp' })
    const saved = JSON.parse(localStorage.getItem('ecosemantic-page') ?? '{}') as { state: { resultCategories: Record<string, string> } }
    expect(saved.state.resultCategories).toEqual({ s1: 'm_gwp' })
    localStorage.removeItem('ecosemantic-page')
  })

  it('chooses an entry and a process, and forgets both when the canvas takes another system', () => {
    useUi.getState().setCanvasSystem('s1')
    useUi.getState().chooseEntry({ systemId: 's1', seq: 2, hash: 'h2' })
    useUi.getState().chooseProcess('p1')
    useUi.getState().setCanvasSystem('s1')
    expect(useUi.getState().chosenEntry?.seq).toBe(2)
    expect(useUi.getState().chosenProcess).toBe('p1')
    useUi.getState().setCanvasSystem('s2')
    expect(useUi.getState().chosenEntry).toBeNull()
    expect(useUi.getState().chosenProcess).toBeNull()
  })

  it('keeps the canvas state on the system it belongs to and clears it when the canvas takes another', () => {
    useUi.getState().setCanvasSystem('s1')
    useUi.getState().setCanvasVariant('heavy')
    useUi.getState().setCanvasSystem('s1')
    expect(useUi.getState().canvasVariant).toBe('heavy')
    useUi.getState().setCanvasSystem('s2')
    expect(useUi.getState().canvasVariant).toBeNull()
  })

  it('counts from the seq last seen, once a page load, and remembers the latest seen', () => {
    useUi.setState({ seen: { s1: 2 }, since: {} })
    useUi.getState().look('s1', 4)
    expect(useUi.getState().since.s1).toBe(2)
    expect(useUi.getState().seen.s1).toBe(4)
    useUi.getState().look('s1', 6)
    expect(useUi.getState().since.s1).toBe(2)
    expect(useUi.getState().seen.s1).toBe(6)
    useUi.getState().markSeen('s1', 6)
    expect(useUi.getState().since.s1).toBe(6)
  })

  it('finds nothing new in a system never seen', () => {
    useUi.setState({ seen: {}, since: {} })
    useUi.getState().look('s2', 3)
    expect(useUi.getState().since.s2).toBe(3)
  })

  it('starts scaled on every load, whatever an earlier visit left persisted', async () => {
    localStorage.setItem('ecosemantic-page', JSON.stringify({ state: { scaledView: false, formulaValues: true }, version: 0 }))
    await useUi.persist.rehydrate()
    expect(useUi.getState().scaledView).toBe(true)
    expect(useUi.getState().formulaValues).toBe(true)
    localStorage.removeItem('ecosemantic-page')
  })
})
