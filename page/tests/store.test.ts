import { PANEL_WIDTH, TRAIL_LENGTH, useUi, type EditorTab } from '@/store/ui'

const tab = (id: string, path = `/systems/1/processes/${id}/general`): EditorTab => ({ id, kind: 'process', title: id, path })

describe('ui store', () => {
  beforeEach(() => {
    useUi.setState({ theme: 'ecosemantic', pinned: [], details: null, lastDetails: null, trail: [], collapsed: {} })
  })

  it('shows a thing in Details and adds it to the trail once', () => {
    useUi.getState().showDetails(tab('a'))
    useUi.getState().showDetails(tab('a'))
    expect(useUi.getState().details?.id).toBe('a')
    expect(useUi.getState().trail.map((t) => t.id)).toEqual(['a'])
  })

  it('cuts the trail back to a thing opened again, and keeps its last steps', () => {
    for (const id of ['a', 'b', 'c']) useUi.getState().showDetails(tab(id))
    useUi.getState().showDetails(tab('b'))
    expect(useUi.getState().trail.map((t) => t.id)).toEqual(['a', 'b'])
    for (const id of ['c', 'd', 'e', 'f']) useUi.getState().showDetails(tab(id))
    expect(useUi.getState().trail).toHaveLength(TRAIL_LENGTH)
    expect(useUi.getState().trail.at(-1)?.id).toBe('f')
  })

  it('opens a collapsed panel beside the graph when Details shows a thing', () => {
    useUi.getState().setPanelMode('collapsed')
    useUi.getState().showDetails(tab('a'))
    expect(useUi.getState().panelMode).toBe('beside')
  })

  it('leaves an expanded panel expanded when Details shows a thing', () => {
    useUi.getState().setPanelMode('expanded')
    useUi.getState().showDetails(tab('a'))
    expect(useUi.getState().panelMode).toBe('expanded')
  })

  it('gives the panel its first width back', () => {
    useUi.getState().setPanelWidth(900)
    useUi.getState().resetPanelWidth()
    expect(useUi.getState().panelWidth).toBe(PANEL_WIDTH)
  })

  it('shows Activity with no trail, and remembers what Details held', () => {
    useUi.getState().showDetails(tab('a'))
    useUi.getState().showActivity()
    expect(useUi.getState().details).toBeNull()
    expect(useUi.getState().trail).toEqual([])
    expect(useUi.getState().lastDetails?.id).toBe('a')
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

  it('stamps the theme on the document', () => {
    useUi.getState().setTheme('openlca')
    expect(document.documentElement.getAttribute('data-theme')).toBe('openlca')
  })

  it('toggles a section', () => {
    useUi.getState().toggleSection('general')
    expect(useUi.getState().collapsed.general).toBe(true)
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
