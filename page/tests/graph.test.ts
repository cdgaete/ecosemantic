/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as url from 'node:url'
import { buildGraph, changedCards, changedSuppliers, droppedCards, hotFrom, edgeText, outlinesFrom } from '@/editors/graph/build'
import { atRest, detailAt, framing, READABLE_ZOOM, revealFor, routePath, viewportFor } from '@/editors/graph/layout'
import { layoutAnswer, routed } from './placements'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import agentSystem from './fixtures/agent_system.json'
import agentLog from './fixtures/agent_log.json'
import type { NodeChange } from '@xyflow/react'
import type { LinkedNodeType, ProcessNodeType } from '@/editors/graph/build'
import systems from './fixtures/systems.json'
import type { LogEntry, ProductSystem } from '@/api/types'

const doc = system.value as ProductSystem

describe('graph', () => {
  it('draws one card per base process and one link per foreground input', () => {
    const { nodes, edges } = buildGraph(doc, routed(doc).value, hotFrom(null), 'widget')
    expect(nodes.map((n) => n.id).sort()).toEqual(doc.processes.map((p) => p.code).sort())
    expect(edges).toHaveLength(1)
    expect(edges[0].source).toBe('frame')
    expect(edges[0].target).toBe('widget')
    expect(nodes.find((n) => n.id === 'widget')?.data.reference).toBe(true)
  })

  it('marks the reference card only when the validation answer names one root', () => {
    const { nodes } = buildGraph(doc, routed(doc).value, hotFrom(null), null)
    expect(nodes.some((n) => n.data.reference)).toBe(false)
  })

  it('draws a link for each foreground input', () => {
    expect(buildGraph(doc, routed(doc).value, hotFrom(null), 'widget').edges).toHaveLength(1)
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
    const { nodes } = buildGraph(doc, routed(doc).value, hot, 'widget')
    expect(nodes.find((n) => n.id === 'widget')?.data.hot).toBe(true)
    expect(nodes.find((n) => n.id === 'widget')?.data.hotExchanges).toEqual([widget.exchanges[1].id])
    expect(nodes.find((n) => n.id === 'frame')?.data.hot).toBe(true)
  })

  it('outlines a card in the colour of the latest entry that changed it or one of its exchanges', () => {
    const built = agentSystem.value as ProductSystem
    const outlines = outlinesFrom(built, agentLog.value as LogEntry[], (entry) => `colour-${entry.seq}`)
    expect(outlines.get('bottle')).toBe('colour-5')
    expect(buildGraph(built, routed(built).value, hotFrom(null), null, outlines).nodes[0].data.outline).toBe('colour-5')
    expect(buildGraph(built, routed(built).value, hotFrom(null), null).nodes[0].data.outline).toBeNull()
  })
})

describe('the arrows the arrangement routes', () => {
  const widget = doc.processes.find((p) => p.code === 'widget')!

  it('draws one arrow per route, from the route\'s provider to its consumer, over the exchange it feeds', () => {
    const arrangement = routed(doc).value
    const { edges } = buildGraph(doc, arrangement, hotFrom(null), 'widget')
    expect(edges.map((e) => ({ id: e.id, source: e.source, target: e.target, targetHandle: e.targetHandle }))).toEqual(
      arrangement.edges.map((r) => ({ id: `flow-${r.exchange_id}`, source: r.provider, target: r.consumer, targetHandle: r.exchange_id })),
    )
    const frame = widget.exchanges.find((e) => e.id === edges[0].targetHandle)!
    expect((edges[0].data as { amount: number; unit: string; formula: string | null }).amount).toBe(frame.amount)
    expect((edges[0].data as { amount: number; unit: string; formula: string | null }).unit).toBe(frame.unit)
    expect((edges[0].data as { amount: number; unit: string; formula: string | null }).formula).toBe(frame.formula)
  })

  it('draws nothing the arrangement does not route, for an input naming a code the system lacks', () => {
    const ghost = { ...widget.exchanges[3], id: 'ghost-exchange', input: { kind: 'foreground' as const, code: 'ghost' } }
    const product: ProductSystem = { ...doc, processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, ghost] } : p)) }
    expect(buildGraph(product, routed(product).value, hotFrom(null), 'widget').edges.map((e) => e.targetHandle)).not.toContain('ghost-exchange')
    expect(buildGraph(product, layoutAnswer(product).value, hotFrom(null), 'widget').edges).toEqual([])
  })

  it('takes a linked card\'s system, pin and case from the exchange its route carries', () => {
    const part = (systems.value as { id: string }[]).find((s) => s.id !== doc.id)!
    const link = { kind: 'system' as const, product_system_id: part.id, at_hash: 'ab'.repeat(32), case: 'light' }
    const linking: ProductSystem = {
      ...doc,
      processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, { ...widget.exchanges[3], id: 'link-a', input: link }] } : p)),
    }
    const arrangement = routed(linking).value
    expect(arrangement.edges.map((r) => r.provider)).toContain(`system:${part.id}`)
    const linked = buildGraph(linking, arrangement, hotFrom(null), 'widget').nodes.find((n) => n.type === 'linked') as LinkedNodeType
    expect(linked.id).toBe(`system:${part.id}`)
    expect(linked.data).toMatchObject({ productSystemId: part.id, atHash: 'ab'.repeat(32), case: 'light' })
  })

  it('draws no card of a linked system the system does not route', () => {
    expect(buildGraph(doc, routed(doc).value, hotFrom(null), 'widget').nodes.some((n) => n.type === 'linked')).toBe(false)
  })
})

const here = path.dirname(url.fileURLToPath(import.meta.url))
const GRAPH = path.resolve(here, '../src/editors/graph')

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return sources(full)
    return /\.tsx?$/.test(entry.name) ? [full] : []
  })
}

const KEY = /(['"`])system:/

describe('a card key', () => {
  it('is a string no file of the graph spells, the arrangement answering it', () => {
    const offenders = sources(GRAPH).flatMap((file) =>
      readFileSync(file, 'utf8')
        .split('\n')
        .flatMap((line, at) => (KEY.test(line) ? [`${path.relative(GRAPH, file)}:${at + 1}: ${line.trim()}`] : [])),
    )
    expect(offenders).toEqual([])
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
    const { nodes, edges } = buildGraph(doc, routed(doc).value, hotFrom(entry), 'widget')
    expect(changedCards(nodes)).toEqual(['widget'])
    expect(changedSuppliers(edges)).toEqual(['frame'])
    expect(changedSuppliers(buildGraph(doc, routed(doc).value, hotFrom(null), 'widget').edges)).toEqual([])
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

describe('viewportFor', () => {
  const drawing = { x: 0, y: 0, width: 2260, height: 370 }
  const reference = { x: 1990, y: 90, width: 270, height: 190 }
  const limits = { min: READABLE_ZOOM, max: 1 }
  const canvasLimits = { min: 0.2, max: 1 }
  const none = { left: 0, top: 0, right: 0, bottom: 0 }

  it('fits the whole drawing inside a clear area too narrow for it at the readable zoom, down to the floor the overview sets', () => {
    const view = viewportFor({ target: drawing, anchor: null, canvas: { width: 579, height: 492 }, clearance: none, zoom: canvasLimits })
    expect(view.zoom).toBeCloseTo(579 / 2260)
    expect(view.zoom).toBeLessThan(READABLE_ZOOM)
    expect(view.x + drawing.x * view.zoom).toBeGreaterThanOrEqual(0)
    expect(view.y + drawing.y * view.zoom).toBeGreaterThanOrEqual(0)
    expect(view.x + (drawing.x + drawing.width) * view.zoom).toBeLessThanOrEqual(579)
    expect(view.y + (drawing.y + drawing.height) * view.zoom).toBeLessThanOrEqual(492)
    expect(view.x).toBeCloseTo(579 / 2 - (drawing.x + drawing.width / 2) * view.zoom)
  })

  it('holds the readable zoom with the reference card at the right edge of a clear area too narrow for the drawing', () => {
    const view = viewportFor({ target: drawing, anchor: reference, canvas: { width: 579, height: 492 }, clearance: none, zoom: limits })
    expect(view.zoom).toBe(READABLE_ZOOM)
    expect(view.x + (reference.x + reference.width) * view.zoom).toBeCloseTo(579)
    expect(view.y).toBeCloseTo(492 / 2 - (drawing.height / 2) * view.zoom)
  })

  it('holds it in a clear area that fits the drawing at four tenths, which it never lands on', () => {
    const view = viewportFor({ target: drawing, anchor: reference, canvas: { width: 951, height: 328 }, clearance: none, zoom: limits })
    expect(951 / drawing.width).toBeLessThan(READABLE_ZOOM)
    expect(view.zoom).toBe(READABLE_ZOOM)
    expect(view.x + (reference.x + reference.width) * view.zoom).toBeCloseTo(951)
    expect(view.y + (drawing.y + drawing.height) * view.zoom).toBeLessThanOrEqual(328)
    expect(view.y + drawing.y * view.zoom).toBeGreaterThanOrEqual(0)
  })

  it('fits the whole drawing inside the clear area at the zoom that fits it, at most full size', () => {
    const target = { x: 0, y: 0, width: 1800, height: 1200 }
    const clearance = { left: 60, top: 60, right: 60, bottom: 60 }
    const view = viewportFor({ target, anchor: target, canvas: { width: 1024, height: 768 }, clearance, zoom: limits })
    expect(view.zoom).toBeCloseTo(904 / 1800)
    expect(view.x).toBeGreaterThanOrEqual(60)
    expect(view.y).toBeGreaterThanOrEqual(60)
    expect(view.x + target.width * view.zoom).toBeLessThanOrEqual(1024 - 60)
    expect(view.y + target.height * view.zoom).toBeLessThanOrEqual(768 - 60)
    expect(viewportFor({ target: { x: 0, y: 0, width: 400, height: 300 }, anchor: null, canvas: { width: 1024, height: 768 }, clearance, zoom: limits }).zoom).toBe(1)
  })

  it('centres a target that the clear area cannot hold at the readable zoom', () => {
    const view = viewportFor({ target: drawing, anchor: null, canvas: { width: 579, height: 492 }, clearance: none, zoom: limits })
    expect(view.zoom).toBe(READABLE_ZOOM)
    expect(view.x + ((drawing.x + drawing.x + drawing.width) / 2) * view.zoom).toBeCloseTo(579 / 2)
    expect(view.y + ((drawing.y + drawing.y + drawing.height) / 2) * view.zoom).toBeCloseTo(492 / 2)
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
    const built = buildGraph(doc, routed(doc).value, hotFrom(entry), null)
    expect(changedCards(built.nodes).sort()).toEqual([process.code, other.code].sort())
  })

  it('names none for no entry', () => {
    const doc = system.value as ProductSystem
    expect(changedCards(buildGraph(doc, routed(doc).value, hotFrom(null), null).nodes)).toEqual([])
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

describe('revealing a card header', () => {
  const CLEAR = { x: 12, y: 12, width: 1000, height: 276 }
  const HEADER = { x: 100, y: 400, width: 300, height: 40 }

  it('moves nothing while the header sits inside the clear area', () => {
    expect(revealFor({ box: HEADER, viewport: { x: 12, y: -200, zoom: 1 }, clear: CLEAR })).toBeNull()
  })

  it('lifts the view just enough to hold a header whose bottom the sheet covers', () => {
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 0, zoom: 1 }, clear: CLEAR })).toEqual({ x: 0, y: -152, zoom: 1 })
  })

  it('drops the view just enough to hold a header past the top edge of the clear area', () => {
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: -500, zoom: 1 }, clear: CLEAR })).toEqual({ x: 0, y: -388, zoom: 1 })
  })

  it('moves sideways just enough to hold a header past either edge', () => {
    expect(revealFor({ box: HEADER, viewport: { x: -200, y: -200, zoom: 1 }, clear: CLEAR })).toEqual({ x: -88, y: -200, zoom: 1 })
    expect(revealFor({ box: HEADER, viewport: { x: 1000, y: -200, zoom: 1 }, clear: CLEAR })).toEqual({ x: 612, y: -200, zoom: 1 })
  })

  it('keeps the zoom it is given, moving the header at that zoom', () => {
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 200, zoom: 0.5 }, clear: CLEAR })).toEqual({ x: 0, y: 68, zoom: 0.5 })
  })

  it('answers nothing for a region with no room or one the header does not fit', () => {
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 0, zoom: 1 }, clear: { ...CLEAR, height: 0 } })).toBeNull()
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 0, zoom: 1 }, clear: { ...CLEAR, width: 0 } })).toBeNull()
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 0, zoom: 1 }, clear: { ...CLEAR, height: 30 } })).toBeNull()
    expect(revealFor({ box: HEADER, viewport: { x: 0, y: 0, zoom: 1 }, clear: { ...CLEAR, width: 200 } })).toBeNull()
  })
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
