import { buildGraph, changedCards, changedSuppliers, droppedCards, hotFrom, edgeText, outlinesFrom } from '@/editors/graph/build'
import { atRest, detailAt, framing, routePath } from '@/editors/graph/layout'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import agentSystem from './fixtures/agent_system.json'
import agentLog from './fixtures/agent_log.json'
import type { NodeChange } from '@xyflow/react'
import type { ProcessNodeType } from '@/editors/graph/build'
import type { LogEntry, ProductSystem } from '@/api/types'

const doc = system.value as ProductSystem

describe('graph', () => {
  it('draws one card per base process and one link per foreground input', () => {
    const { nodes, edges } = buildGraph(doc, hotFrom(null), 'widget')
    expect(nodes.map((n) => n.id).sort()).toEqual(doc.processes.map((p) => p.code).sort())
    expect(edges).toHaveLength(1)
    expect(edges[0].source).toBe('frame')
    expect(edges[0].target).toBe('widget')
    expect(nodes.find((n) => n.id === 'widget')?.data.reference).toBe(true)
  })

  it('marks the reference card only when the validation answer names one root', () => {
    const { nodes } = buildGraph(doc, hotFrom(null), null)
    expect(nodes.some((n) => n.data.reference)).toBe(false)
  })

  it('draws a link for each foreground input', () => {
    expect(buildGraph(doc, hotFrom(null), 'widget').edges).toHaveLength(1)
  })

  it('marks what the latest entry changed, processes by id and exchanges by id', () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const frame = doc.processes.find((p) => p.code === 'frame')!
    const entry: LogEntry = {
      ...(log.value[0] as LogEntry),
      changes: [
        { op: 'update', entity: 'exchange', id: widget.exchanges[1].id, field: 'amount', before: 1, after: 2 },
        { op: 'add', entity: 'process', id: frame.id, field: null, before: null, after: null },
      ],
    }
    const hot = hotFrom(entry)
    expect(hot.processes.has(frame.id)).toBe(true)
    const { nodes } = buildGraph(doc, hot, 'widget')
    expect(nodes.find((n) => n.id === 'widget')?.data.hot).toBe(true)
    expect(nodes.find((n) => n.id === 'widget')?.data.hotExchanges).toEqual([widget.exchanges[1].id])
    expect(nodes.find((n) => n.id === 'frame')?.data.hot).toBe(true)
  })

  it('outlines a card in the colour of the latest entry that changed it or one of its exchanges', () => {
    const built = agentSystem.value as ProductSystem
    const outlines = outlinesFrom(built, agentLog.value as LogEntry[], (entry) => `colour-${entry.seq}`)
    expect(outlines.get('bottle')).toBe('colour-5')
    expect(buildGraph(built, hotFrom(null), null, outlines).nodes[0].data.outline).toBe('colour-5')
    expect(buildGraph(built, hotFrom(null), null).nodes[0].data.outline).toBeNull()
  })
})

describe('detailAt', () => {
  it('shows a card as its header alone while the canvas is zoomed out past reading its rows', () => {
    expect(detailAt(1)).toBe('rows')
    expect(detailAt(0.5)).toBe('rows')
    expect(detailAt(0.49)).toBe('header')
    expect(detailAt(0.2)).toBe('header')
  })
})

describe('changedSuppliers', () => {
  it('names the card each arrow the latest entry added comes from', () => {
    // the widget's input from the frame is the one foreground arrow
    const entry = { ...(log.value[0] as LogEntry), changes: [{ op: 'add', entity: 'exchange', id: '73b7d6fd-7d08-53d6-bd18-093e6cd44574', field: null, before: null, after: null }] } as LogEntry
    const { nodes, edges } = buildGraph(doc, hotFrom(entry), 'widget')
    expect(changedCards(nodes)).toEqual(['widget'])
    expect(changedSuppliers(edges)).toEqual(['frame'])
    expect(changedSuppliers(buildGraph(doc, hotFrom(null), 'widget').edges)).toEqual([])
  })
})

describe('framing', () => {
  const card = { width: 300, height: 200 }
  it('frames the changed card with its supplier while both fit large enough to read', () => {
    expect(framing(card, { width: 900, height: 200 }, { width: 1360, height: 900 })).toBe('suppliers')
  })

  it('frames the changed card alone when its supplier is too far to keep both readable', () => {
    expect(framing(card, { width: 2300, height: 400 }, { width: 1360, height: 900 })).toBe('changed')
  })

  it('fits the whole drawing when the changed cards do not fit at a readable zoom', () => {
    expect(framing({ width: 2800, height: 400 }, { width: 2800, height: 400 }, { width: 1360, height: 900 })).toBe('whole')
  })

  it('frames the changed card when the canvas has not been measured', () => {
    expect(framing(card, { width: 900, height: 200 }, { width: 0, height: 0 })).toBe('changed')
  })
})

describe('droppedCards', () => {
  const node = (id: string, x: number, y: number) => ({ id, position: { x, y } }) as ProcessNodeType

  it('names only the cards a drag let go of, with where they landed', () => {
    const nodes = [node('widget', 10, 20), node('frame', 30, 40)]
    const changes: NodeChange<ProcessNodeType>[] = [
      { type: 'position', id: 'widget', dragging: false },
      { type: 'position', id: 'frame', dragging: true },
    ]
    expect(droppedCards(changes, nodes)).toEqual([{ code: 'widget', x: 10, y: 20 }])
  })

  it('names none while a drag is still under way, and none for a change of another kind', () => {
    const nodes = [node('widget', 10, 20)]
    expect(droppedCards([{ type: 'position', id: 'widget', dragging: true }], nodes)).toEqual([])
    expect(droppedCards([{ type: 'select', id: 'widget', selected: true }], nodes)).toEqual([])
  })
})

describe('changedCards', () => {
  it('names the cards an entry changed, by a process or by one of its exchanges', () => {
    const doc = system.value as ProductSystem
    const process = doc.processes[0]
    const other = doc.processes[1]
    const entry = { ...log.value[0], changes: [{ ...log.value[0].changes[0], entity: 'exchange', id: other.exchanges[0].id }, { ...log.value[0].changes[0], entity: 'process', id: process.id }] } as LogEntry
    const built = buildGraph(doc, hotFrom(entry), null)
    expect(changedCards(built.nodes).sort()).toEqual([process.code, other.code].sort())
  })

  it('names none for no entry', () => {
    const doc = system.value as ProductSystem
    expect(changedCards(buildGraph(doc, hotFrom(null), null).nodes)).toEqual([])
  })
})

it('draws a route as straight runs between its corners', () => {
  expect(routePath([[0, 0], [40, 0], [40, 30], [100, 30]])).toBe('M 0 0 L 40 0 L 40 30 L 100 30')
})

it('holds an arrow at rest only while both its cards sit where the layout placed them', () => {
  const placed = new Map([
    ['a', { x: 0, y: 40 }],
    ['b', { x: 420, y: 40 }],
  ])
  expect(atRest('a', 'b', placed, new Map([['a', { x: 0, y: 40 }], ['b', { x: 420, y: 40 }]]))).toBe(true)
  expect(atRest('a', 'b', placed, new Map([['a', { x: 0, y: 43 }], ['b', { x: 420, y: 40 }]]))).toBe(false)
  expect(atRest('a', 'b', placed, new Map([['a', { x: 0, y: 40 }], ['b', { x: 421, y: 40 }]]))).toBe(false)
  expect(atRest('a', 'b', placed, new Map([['a', { x: 0, y: 40 }]]))).toBe(false)
  expect(atRest('a', 'c', placed, new Map([['a', { x: 0, y: 40 }], ['c', { x: 0, y: 0 }]]))).toBe(false)
})

describe('edge label text', () => {
  const label = { x: 1, y: 2, width: 3, height: 4, per_unit: '0.25 kg per unit', scaled: '1.25 kg', formula: null }
  it('is the scaled text when the scaled view is on and the server wrote one, else the per-unit text', () => {
    expect(edgeText(label, true, true)).toEqual({ x: 1, y: 2, width: 3, height: 4, text: '1.25 kg' })
    expect(edgeText(label, false, true).text).toBe('0.25 kg per unit')
    expect(edgeText({ ...label, scaled: null }, true, true).text).toBe('0.25 kg per unit')
  })
  it('is the formula text in either view while Formula values is off, and the value while it is on', () => {
    const formula = { ...label, formula: 'ƒ kWh' }
    expect(edgeText(formula, true, false).text).toBe('ƒ kWh')
    expect(edgeText(formula, false, false).text).toBe('ƒ kWh')
    expect(edgeText(formula, true, true).text).toBe('1.25 kg')
    expect(edgeText(formula, false, true).text).toBe('0.25 kg per unit')
    expect(edgeText(label, true, false).text).toBe('1.25 kg')
  })
})
