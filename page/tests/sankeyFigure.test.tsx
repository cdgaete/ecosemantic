import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Position, ReactFlowProvider } from '@xyflow/react'
import type { ContributionResult, TreeNode } from '@/api/types'
import { Link, Sankey } from '@/editors/results/figures/Sankey'
import { NODE_H, NODE_W, linkWidth, sankeyElements, sankeyFromTree } from '@/editors/results/figures/sankey'
import byPath from './fixtures/contributions_path.json'

const tree = (byPath.value as ContributionResult).root!
const figure = sankeyFromTree(tree)

function processNode(ref: TreeNode['ref'], name: string, level: number): TreeNode {
  return { kind: 'process', ref, name, location: null, score: 1, fraction: null, level, children: [] }
}

const banded: TreeNode = {
  ...processNode({ kind: 'foreground', code: 'widget' }, 'widget', 0),
  score: 4,
  fraction: 1,
  children: [
    processNode({ kind: 'background', database: 'fixture', id: 'steel' }, 'steel', 1),
    processNode({ kind: 'foreground', code: 'frame' }, 'frame', 1),
    processNode({ kind: 'foreground', code: 'gizmo' }, 'gizmo', 1),
  ],
}

const STAGES = new Map([
  ['widget', 'assembly'],
  ['frame', 'materials'],
])

const staged = sankeyFromTree(banded, (code) => STAGES.get(code) ?? null)

function bandStroke(stages: string[] | undefined, stage: string | null): string {
  const props = {
    id: 'band',
    source: 'root',
    target: 'root/1',
    sourceX: 0,
    sourceY: 0,
    targetX: 120,
    targetY: 90,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    data: { width: 12, offset: 4, stage },
    ...(stages === undefined ? {} : { stages }),
  }
  const { container } = render(
    <ReactFlowProvider>
      <svg>
        <Link {...(props as unknown as Parameters<typeof Link>[0])} />
      </svg>
    </ReactFlowProvider>,
  )
  return container.querySelector('path.react-flow__edge-path')?.getAttribute('style') ?? ''
}

it('colours a band by the stage of the split, and a band of no stage with the muted token', () => {
  const stages = ['assembly', 'materials']
  const materials = staged.links.find((link) => link.stage === 'materials')!
  const unstaged = staged.links.find((link) => link.stage === null)!
  expect(bandStroke(stages, 'assembly')).toContain('rgb(var(--stage-1) / 0.6)')
  expect(bandStroke(stages, materials.stage)).toContain('rgb(var(--stage-2) / 0.6)')
  expect(bandStroke(stages, unstaged.stage)).toContain('rgb(var(--muted-foreground) / 0.6)')
})

it('draws a band with the plain link token while it holds no stage name', () => {
  expect(bandStroke(undefined, 'materials')).toContain('rgb(var(--link-stroke) / 0.6)')
  expect(bandStroke([], null)).toContain('rgb(var(--link-stroke) / 0.6)')
})

interface Rect {
  x: number
  y: number
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + NODE_W && b.x < a.x + NODE_W && a.y < b.y + NODE_H && b.y < a.y + NODE_H
}

function depthOf(id: string): number {
  return id.split('/').length - 1
}

it('places every card without overlap, root on top and centred over its children', () => {
  const { nodes } = sankeyElements(figure.nodes, figure.links)
  expect(nodes).toHaveLength(figure.nodes.length)
  const at = new Map(nodes.map((n) => [n.id, n.position]))
  const root = at.get('root')!
  for (const [id, spot] of at) if (id !== 'root') expect(spot.y).toBeGreaterThan(root.y)
  const ids = [...at.keys()]
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) expect(overlaps(at.get(ids[i])!, at.get(ids[j])!)).toBe(false)
  const children = figure.links.filter((l) => l.source === 'root').map((l) => l.target)
  const centre = (id: string) => at.get(id)!.x + NODE_W / 2
  expect(centre('root')).toBeCloseTo((centre(children[0]) + centre(children[children.length - 1])) / 2)
  for (const node of nodes) expect([node.width, node.height]).toEqual([NODE_W, NODE_H])
})

it('measures the extent of the drawing, so the figure takes its proportions', () => {
  const { nodes, extent } = sankeyElements(figure.nodes, figure.links)
  expect(extent.width).toBe(Math.max(...nodes.map((n) => n.position.x)) + NODE_W)
  expect(extent.height).toBe(Math.max(...nodes.map((n) => n.position.y)) + NODE_H)
})

it('rows every card by its tree depth', () => {
  const { nodes } = sankeyElements(figure.nodes, figure.links)
  const byDepth = new Map<number, number[]>()
  for (const node of nodes) byDepth.set(depthOf(node.id), [...(byDepth.get(depthOf(node.id)) ?? []), node.position.y])
  for (const ys of byDepth.values()) for (const y of ys) expect(y).toBe(ys[0])
})

it('draws a link per child, as wide as its share, leaving its parent along the bottom edge', () => {
  const { edges } = sankeyElements(figure.nodes, figure.links)
  expect(edges).toHaveLength(figure.links.length)
  const fractions = new Map(figure.nodes.map((n) => [n.id, n.fraction]))
  for (const edge of edges) {
    expect(edge.data!.width).toBe(linkWidth(fractions.get(edge.target)!))
    expect(Math.abs(edge.data!.offset)).toBeLessThanOrEqual(NODE_W / 2)
  }
})

it('draws the cards on a canvas a person zooms and pans, never in a scrolling box', () => {
  const { container } = render(<Sankey nodes={figure.nodes} links={figure.links} unit="kg CO2-Eq" />)
  const drawn = screen.getByRole('figure', { name: /Sankey diagram/ })
  for (const node of figure.nodes) expect(within(drawn).getAllByText(node.name).length).toBeGreaterThan(0)
  expect(within(drawn).getByRole('button', { name: /zoom in/i })).toBeInTheDocument()
  expect(within(drawn).getByRole('button', { name: /zoom out/i })).toBeInTheDocument()
  expect(within(drawn).getByRole('button', { name: /fit view/i })).toBeInTheDocument()
  expect(container.querySelector('.overflow-auto')).toBeNull()
})

it('opens the diagram large from its Expand control, and closes it again', async () => {
  render(<Sankey nodes={figure.nodes} links={figure.links} unit="kg CO2-Eq" title="climate change" />)
  fireEvent.click(screen.getByRole('button', { name: 'Expand diagram' }))
  const large = await screen.findByRole('dialog', { name: /Sankey diagram/ })
  expect(within(large).getByText(/climate change/)).toBeInTheDocument()
  for (const node of figure.nodes) expect(within(large).getAllByText(node.name).length).toBeGreaterThan(0)
  expect(within(large).queryByRole('button', { name: 'Expand diagram' })).toBeNull()
  fireEvent.click(within(large).getByRole('button', { name: 'Close' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})
