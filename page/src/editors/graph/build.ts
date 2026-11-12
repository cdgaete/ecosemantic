import { MarkerType, type Edge, type Node, type NodeChange } from '@xyflow/react'
import type { EdgeText } from './FlowEdge'
import type { Arrangement, CardGeometry, Exchange, Label, LogEntry, Placement, Process, ProductSystem, Route } from '@/api/types'

export interface ProcessNodeData extends Record<string, unknown> {
  process: Process
  reference: boolean
  hot: boolean
  hotExchanges: string[]
  outline: string | null
  systemId: string
  placement: Placement
  card: CardGeometry
}

export type ProcessNodeType = Node<ProcessNodeData, 'process'>

export interface LinkedNodeData extends Record<string, unknown> {
  productSystemId: string
  atHash: string | null
  case: string | null
  placement: Placement
  card: CardGeometry
}

export type LinkedNodeType = Node<LinkedNodeData, 'linked'>

export type GraphNode = ProcessNodeType | LinkedNodeType

type Unplaced<N extends GraphNode> = Omit<N, 'data'> & { data: { [K in keyof N['data'] as K extends 'placement' | 'card' ? never : K]: N['data'][K] } }

export type BuiltNode = Unplaced<ProcessNodeType> | Unplaced<LinkedNodeType>

export interface Hot {
  processes: Set<string>
  exchanges: Set<string>
}

export function hotFrom(entry: LogEntry | null): Hot {
  const hot: Hot = { processes: new Set(), exchanges: new Set() }
  for (const change of entry?.changes ?? []) {
    if (change.entity === 'process') hot.processes.add(change.id)
    if (change.entity === 'exchange') hot.exchanges.add(change.id)
  }
  return hot
}

export function changedCards(nodes: BuiltNode[]): string[] {
  return nodes.filter((node) => node.type === 'process' && node.data.hot).map((node) => node.id)
}

export function changedSuppliers(edges: Edge[]): string[] {
  return [...new Set(edges.filter((edge) => edge.className === 'hot').map((edge) => edge.source))]
}

export function droppedCards(changes: NodeChange<GraphNode>[], nodes: GraphNode[]): { code: string; x: number; y: number }[] {
  const dropped = new Set(changes.flatMap((change) => (change.type === 'position' && change.dragging === false ? [change.id] : [])))
  return nodes.filter((node) => dropped.has(node.id)).map((node) => ({ code: node.id, x: node.position.x, y: node.position.y }))
}

export function edgeText(label: Label, scaled: boolean, formulaValues: boolean): EdgeText {
  const text = !formulaValues && label.formula !== null ? label.formula : scaled && label.scaled !== null ? label.scaled : label.per_unit
  return { x: label.x, y: label.y, width: label.width, height: label.height, text }
}

export type Outlines = Map<string, string>

const NONE: Outlines = new Map()

function exchangesOf(system: ProductSystem): Map<string, Exchange> {
  return new Map(system.processes.flatMap((process) => process.exchanges.map((exchange) => [exchange.id, exchange] as [string, Exchange])))
}

function arrows(routes: Route[], exchanges: Map<string, Exchange>, hot: Hot): Edge[] {
  return routes.flatMap((route) => {
    const exchange = exchanges.get(route.exchange_id)
    if (exchange === undefined) return []
    return [
      {
        id: `flow-${route.exchange_id}`,
        source: route.provider,
        target: route.consumer,
        sourceHandle: 'out',
        targetHandle: route.exchange_id,
        type: 'flow',
        data: { amount: exchange.amount, unit: exchange.unit, formula: exchange.formula, points: null, rest: false, label: null },
        markerEnd: { type: MarkerType.ArrowClosed },
        className: hot.exchanges.has(route.exchange_id) ? 'hot' : undefined,
      },
    ]
  })
}

function linkedNodes(system: ProductSystem, routes: Route[], exchanges: Map<string, Exchange>): Unplaced<LinkedNodeType>[] {
  const codes = new Set(system.processes.map((process) => process.code))
  const found = new Map<string, Unplaced<LinkedNodeType>>()
  for (const route of routes) {
    if (codes.has(route.provider) || found.has(route.provider)) continue
    const input = exchanges.get(route.exchange_id)?.input
    if (input?.kind !== 'system') continue
    found.set(route.provider, {
      id: route.provider,
      type: 'linked',
      position: { x: 0, y: 0 },
      data: { productSystemId: input.product_system_id, atHash: input.at_hash, case: input.case },
    })
  }
  return [...found.values()]
}

export function outlinesFrom(system: ProductSystem, entries: LogEntry[], colour: (entry: LogEntry) => string): Outlines {
  const owner = new Map<string, string>()
  for (const process of system.processes) {
    owner.set(process.id, process.code)
    for (const exchange of process.exchanges) owner.set(exchange.id, process.code)
  }
  const outlines: Outlines = new Map()
  for (const entry of [...entries].sort((a, b) => a.seq - b.seq))
    for (const change of entry.changes) {
      const code = owner.get(change.id)
      if (code !== undefined) outlines.set(code, colour(entry))
    }
  return outlines
}

function processNode(process: Process, system: ProductSystem, hot: Hot, reference: boolean, outlines: Outlines): Unplaced<ProcessNodeType> {
  const hotExchanges = process.exchanges.filter((e) => hot.exchanges.has(e.id)).map((e) => e.id)
  return {
    id: process.code,
    type: 'process',
    position: { x: 0, y: 0 },
    data: { process, reference, hot: hot.processes.has(process.id) || hotExchanges.length > 0, hotExchanges, outline: outlines.get(process.code) ?? null, systemId: system.id },
  }
}

export function buildGraph(system: ProductSystem, arrangement: Arrangement, hot: Hot, reference: string | null, outlines: Outlines = NONE): { nodes: BuiltNode[]; edges: Edge[] } {
  const exchanges = exchangesOf(system)
  const nodes: BuiltNode[] = system.processes.map((process) => processNode(process, system, hot, process.code === reference, outlines))
  nodes.push(...linkedNodes(system, arrangement.edges, exchanges))
  return { nodes, edges: arrows(arrangement.edges, exchanges, hot) }
}
