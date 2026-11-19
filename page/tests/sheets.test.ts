import type { SheetKind } from '@/store/ui'
import { originAfter, returnLabel, sheetOf, systemOf, type Place } from '@/window/sheets'

const GRAPH: Place = { address: '/systems/s1', kind: null }
const FORM: Place = { address: '/systems/s1/results/setup', kind: null }
const RESULT: Place = { address: '/systems/s1/results/impact?call=c1', kind: 'results' }
const TREE: Place = { address: '/systems/s1/results/tree?call=c1', kind: 'results' }
const EXPLORER: Place = { address: '/databases/fixture/datasets', kind: 'explorer' }
const FLOWS: Place = { address: '/databases/fixture/flows', kind: 'explorer' }
const NONE: Record<SheetKind, string | null> = { explorer: null, results: null }

describe('sheetOf', () => {
  it.each([
    ['/databases/fixture/datasets', 'explorer'],
    ['/databases/fixture/processes/p1', 'explorer'],
    ['/systems/s1/results/impact', 'results'],
    ['/systems/s1/results/sankey', 'results'],
    ['/systems/s1/simulations/r1', 'results'],
    ['/systems/s1/results', null],
    ['/systems/s1/results/setup', null],
    ['/systems/s1/simulations', null],
    ['/systems/s1/datasets/fixture/p1', null],
    ['/systems/s1', null],
    ['/databases', null],
    ['/', null],
  ])('answers %s as %s', (pathname, kind) => {
    expect(sheetOf(pathname)).toBe(kind)
  })
})

describe('originAfter', () => {
  it('gives a sheet opened at its own address no origin', () => {
    expect(originAfter(null, RESULT, NONE)).toBeNull()
  })

  it('gives a sheet the address it was opened from', () => {
    expect(originAfter(FORM, RESULT, NONE)).toBe(FORM.address)
    expect(originAfter(GRAPH, EXPLORER, NONE)).toBe(GRAPH.address)
  })

  it('keeps the origin while the person moves inside the sheet, and changes nothing outside one', () => {
    expect(originAfter(RESULT, TREE, { explorer: null, results: FORM.address })).toBeUndefined()
    expect(originAfter(EXPLORER, FLOWS, { explorer: GRAPH.address, results: null })).toBeUndefined()
    expect(originAfter(RESULT, GRAPH, { explorer: null, results: FORM.address })).toBeUndefined()
  })

  it('opens the explorer over a result, and keeps the origin of the result when the person comes back into it', () => {
    const over = { explorer: null, results: FORM.address }
    expect(originAfter(RESULT, EXPLORER, over)).toBe(RESULT.address)
    const under = { explorer: RESULT.address, results: FORM.address }
    expect(originAfter(EXPLORER, RESULT, under)).toBeUndefined()
    expect(originAfter(FLOWS, TREE, under)).toBeUndefined()
  })

  it('gives a result opened from an explorer that was not over one the explorer as its origin', () => {
    expect(originAfter(EXPLORER, RESULT, { explorer: GRAPH.address, results: null })).toBe(EXPLORER.address)
  })
})

describe('returnLabel', () => {
  it.each([
    ['/systems/s1', 'Back to graph'],
    ['/systems/s1/results/setup', 'Back to graph'],
    ['/systems/s1/processes/p1/io?x=1', 'Back to graph'],
    ['/databases/fixture/datasets?node=24', 'Back to the explorer'],
    ['/', 'Back to product systems'],
    ['/databases', 'Back to databases'],
    ['/nowhere', 'Back'],
  ])('names %s as %s', (address, label) => {
    expect(returnLabel(address)).toBe(label)
  })
})

describe('systemOf', () => {
  it('answers the system an address is under, and none for a list or a database', () => {
    expect(systemOf('/systems/s1/results/impact?call=c1')).toBe('s1')
    expect(systemOf('/systems/s1')).toBe('s1')
    expect(systemOf('/databases/fixture/datasets')).toBeNull()
    expect(systemOf('/')).toBeNull()
  })
})
