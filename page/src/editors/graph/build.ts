import { MarkerType, Position, type Edge, type Node, type NodeChange } from '@xyflow/react'
import type { EdgeText } from './FlowEdge'
import type { Arrangement, CardGeometry, ContributionResult, Exchange, Label, LogEntry, Placement, Process, ProductSystem, Route, StageRegions } from '@/api/types'
import { formatAmount, formatShare } from '@/lib/format'
import { stageColour } from '@/lib/stageColours'

export interface OwnShown {
  score: number
  fraction: number | null
  unit: string
}

export interface Supplies {
  processes: number
  stages: number
}

export interface Rows {
  expanded: boolean
  toggle: (code: string) => void
}

export interface ProcessNodeData extends Record<string, unknown> {
  process: Process
  reference: boolean
  hot: boolean
  hotExchanges: string[]
  outline: string | null
  systemId: string
  placement: Placement
  card: CardGeometry
  own: OwnShown | null
  supplies: Supplies | null
  rows: Rows
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

export interface StageNodeData extends Record<string, unknown> {
  stage: string
  colour: string
  fill: string
  line: string
  label: string
}

export type StageNodeType = Node<StageNodeData, 'stage'>

export type GraphNode = ProcessNodeType | LinkedNodeType | StageNodeType

export const STAGE_PREFIX = 'stage:'

export function stageNodeId(stage: string, region: number): string {
  return `${STAGE_PREFIX}${stage}:${region}`
}

type Unplaced<N extends GraphNode> = Omit<N, 'data'> & { data: { [K in keyof N['data'] as K extends 'placement' | 'card' | 'rows' ? never : K]: N['data'][K] } }

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
  return nodes.filter((node) => dropped.has(node.id) && node.type !== 'stage').map((node) => ({ code: node.id, x: node.position.x, y: node.position.y }))
}

function stageLabel(stage: string, split: ContributionResult | undefined): string {
  const part = split?.stages?.find((one) => one.stage === stage)
  if (split === undefined || part === undefined) return stage
  return `${stage} · ${formatShare(part.fraction)} · ${formatAmount(part.score)} ${split.total.unit}`
}

/** Each stage's regions as boxes behind the cards, in its colour and labelled with its part of the split. */
export function stageNodes(stages: StageRegions[], split?: ContributionResult): StageNodeType[] {
  const names = stages.map((one) => one.stage)
  return stages.flatMap((one) =>
    one.regions.map((region, at) => ({
      id: stageNodeId(one.stage, at),
      type: 'stage' as const,
      position: { x: region.x, y: region.y },
      width: region.width,
      height: region.height,
      zIndex: -1,
      selectable: false,
      draggable: false,
      connectable: false,
      focusable: false,
      style: { pointerEvents: 'none' },
      handles: [
        { id: 'out', type: 'source' as const, position: Position.Right, x: region.width, y: region.height / 2, width: 0, height: 0 },
        { id: 'in', type: 'target' as const, position: Position.Left, x: 0, y: region.height / 2, width: 0, height: 0 },
      ],
      data: {
        stage: one.stage,
        colour: stageColour(names, one.stage),
        fill: stageColour(names, one.stage, 0.07),
        line: stageColour(names, one.stage, 0.6),
        label: stageLabel(one.stage, split),
      },
    })),
  )
}

/** Dashed lines joining each stage's first region to its others, in the stage's colour. */
export function tetherEdges(stages: StageRegions[]): Edge[] {
  const names = stages.map((one) => one.stage)
  const edges: Edge[] = []
  for (const one of stages)
    for (let at = 1; at < one.regions.length; at += 1)
      edges.push({
        id: `tether:${one.stage}:${at}`,
        source: stageNodeId(one.stage, 0),
        target: stageNodeId(one.stage, at),
        type: 'tether',
        selectable: false,
        focusable: false,
        style: { stroke: stageColour(names, one.stage, 0.6), strokeWidth: 1.5, strokeDasharray: '5 4' },
      })
  return edges
}

export function edgeText(label: Label, scaled: boolean, formulaValues: boolean): EdgeText {
  const text = !formulaValues && label.formula !== null ? label.formula : scaled && label.scaled !== null ? label.scaled : label.per_unit
  return { x: label.x, y: label.y, width: label.width, height: label.height, text }
}

export type Outlines = Map<string, string>

const NONE: Outlines = new Map()

/** Each own process of the split by its code, with the part it holds of the split's total. */
export function ownParts(split: ContributionResult | undefined): Map<string, OwnShown> {
  const parts = new Map<string, OwnShown>()
  if (split === undefined) return parts
  for (const stage of split.stages ?? [])
    for (const process of stage.processes) parts.set(process.ref.code, { score: process.score, fraction: process.fraction, unit: split.total.unit })
  return parts
}

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
    data: { process, reference, hot: hot.processes.has(process.id) || hotExchanges.length > 0, hotExchanges, outline: outlines.get(process.code) ?? null, systemId: system.id, own: null, supplies: null },
  }
}

export function buildGraph(system: ProductSystem, arrangement: Arrangement, hot: Hot, reference: string | null, outlines: Outlines = NONE): { nodes: BuiltNode[]; edges: Edge[] } {
  const exchanges = exchangesOf(system)
  const nodes: BuiltNode[] = system.processes.map((process) => processNode(process, system, hot, process.code === reference, outlines))
  nodes.push(...linkedNodes(system, arrangement.edges, exchanges))
  return { nodes, edges: arrows(arrangement.edges, exchanges, hot) }
}
