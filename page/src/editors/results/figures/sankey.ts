import type { Edge, Node } from '@xyflow/react'
import type { TreeNode } from '@/api/types'

export interface SankeyNodeDatum {
  id: string
  name: string
  location: string | null
  score: number
  fraction: number
  depth: number
}

export interface SankeyLinkDatum {
  source: string
  target: string
  value: number
}

const MAX_LINK_WIDTH = 70

export function linkWidth(fraction: number): number {
  return Math.max(1, Math.min(MAX_LINK_WIDTH, Math.ceil(Math.abs(fraction) * MAX_LINK_WIDTH)))
}

export const NODE_W = 220
export const NODE_H = 76
const ROW_GAP = 90
const NODE_GAP = 40

export interface TreePlacement {
  x: number
  y: number
}

export function treeLayout(nodes: SankeyNodeDatum[], links: SankeyLinkDatum[]): Map<string, TreePlacement> {
  const children = new Map<string, string[]>()
  for (const link of links) children.set(link.source, [...(children.get(link.source) ?? []), link.target])
  const targets = new Set(links.map((link) => link.target))
  const slots = new Map<string, number>()
  let leaves = 0
  const place = (id: string): number => {
    const below = (children.get(id) ?? []).map(place)
    const slot = below.length === 0 ? leaves++ : (below[0] + below[below.length - 1]) / 2
    slots.set(id, slot)
    return slot
  }
  for (const node of nodes) if (!targets.has(node.id)) place(node.id)
  const top = Math.min(...nodes.map((node) => node.depth))
  return new Map(nodes.map((node) => [node.id, { x: (slots.get(node.id) ?? 0) * (NODE_W + NODE_GAP), y: (node.depth - top) * (NODE_H + ROW_GAP) }]))
}

export interface SankeyCardData extends Record<string, unknown> {
  datum: SankeyNodeDatum
  unit: string
}

export interface SankeyLinkData extends Record<string, unknown> {
  width: number
  offset: number
}

export type SankeyCard = Node<SankeyCardData, 'card'>
export type SankeyLink = Edge<SankeyLinkData, 'link'>

export function sankeyElements(
  nodes: SankeyNodeDatum[],
  links: SankeyLinkDatum[],
  unit = '',
): { nodes: SankeyCard[]; edges: SankeyLink[]; extent: { width: number; height: number } } {
  const placed = treeLayout(nodes, links)
  const spots = [...placed.values()]
  const extent = { width: Math.max(...spots.map((s) => s.x)) + NODE_W, height: Math.max(...spots.map((s) => s.y)) + NODE_H }
  const family = new Map<string, string[]>()
  for (const link of links) family.set(link.source, [...(family.get(link.source) ?? []), link.target])
  const fractions = new Map(nodes.map((node) => [node.id, node.fraction]))
  return {
    extent,
    nodes: nodes.map((datum) => ({ id: datum.id, type: 'card', position: placed.get(datum.id)!, data: { datum, unit }, width: NODE_W, height: NODE_H, draggable: false, selectable: false })),
    edges: links.map((link) => {
      const siblings = family.get(link.source)!
      const slot = siblings.indexOf(link.target)
      return {
        id: link.target,
        source: link.source,
        target: link.target,
        type: 'link',
        data: { width: linkWidth(fractions.get(link.target)!), offset: ((slot + 0.5) / siblings.length - 0.5) * NODE_W },
      }
    }),
  }
}

export function sankeyFromTree(root: TreeNode): { nodes: SankeyNodeDatum[]; links: SankeyLinkDatum[] } {
  const nodes: SankeyNodeDatum[] = []
  const links: SankeyLinkDatum[] = []
  const walk = (node: TreeNode, id: string) => {
    nodes.push({ id, name: node.name, location: node.location, score: node.score, fraction: node.fraction, depth: node.level })
    node.children.forEach((child, i) => {
      if (child.kind !== 'process') return
      const childId = `${id}/${i}`
      links.push({ source: id, target: childId, value: Math.max(Math.abs(child.score), Number.MIN_VALUE) })
      walk(child, childId)
    })
  }
  walk(root, 'root')
  return { nodes, links }
}
