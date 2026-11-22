import type { ContributionResult, TreeNode } from '@/api/types'
import { linkWidth, sankeyFromTree } from '@/editors/results/figures/sankey'
import byPath from './fixtures/contributions_path.json'

const tree = (byPath.value as ContributionResult).root!

function processNode(ref: TreeNode['ref'], name: string, level: number, children: TreeNode[] = []): TreeNode {
  return { kind: 'process', ref, name, location: null, score: 1, fraction: null, level, children }
}

const hanging = processNode({ kind: 'foreground', code: 'widget' }, 'widget', 0, [
  processNode({ kind: 'background', database: 'fixture', id: 'steel' }, 'steel', 1),
  processNode({ kind: 'foreground', code: 'frame' }, 'frame', 1, [
    processNode({ kind: 'background', database: 'fixture', id: 'aluminium' }, 'aluminium', 2),
    processNode({ kind: 'linked', product_system_id: 'other', at_hash: '07a6bf4d', code: 'door' }, 'door', 2),
  ]),
])

const STAGES = new Map([
  ['widget', 'assembly'],
  ['frame', 'materials'],
])

it('a band takes the stage of the foreground process it hangs under', () => {
  const { nodes, links } = sankeyFromTree(hanging, (code) => STAGES.get(code) ?? null)
  const stages = new Map(nodes.map((node) => [node.id, node.stage]))
  expect(stages.get('root')).toBe('assembly')
  expect(stages.get('root/0')).toBe('assembly')
  expect(stages.get('root/1')).toBe('materials')
  expect(stages.get('root/1/0')).toBe('materials')
  expect(stages.get('root/1/1')).toBe('materials')
  expect(links.map((link) => [link.target, link.stage])).toEqual([
    ['root/0', 'assembly'],
    ['root/1', 'materials'],
    ['root/1/0', 'materials'],
    ['root/1/1', 'materials'],
  ])
  expect(sankeyFromTree({ ...hanging, ref: null }, () => 'assembly').nodes[0].stage).toBeNull()
  expect(sankeyFromTree(hanging).nodes.map((node) => node.stage)).toEqual([null, null, null, null, null])
  expect(sankeyFromTree(hanging).links.map((link) => link.stage)).toEqual([null, null, null, null])
})

it('turns the path tree into process nodes with their returned scores and links weighted by magnitude', () => {
  const { nodes, links } = sankeyFromTree(tree)
  expect(nodes[0].name).toBe(tree.name)
  expect(nodes[0].score).toBe(tree.score)
  expect(links.every((l) => l.value > 0)).toBe(true)
  expect(links.every((l) => nodes.some((n) => n.id === l.source) && nodes.some((n) => n.id === l.target))).toBe(true)
  const processChildren = tree.children.filter((c) => c.kind === 'process')
  expect(links.filter((l) => l.source === nodes[0].id)).toHaveLength(processChildren.length)
})

it.each([
  [0, 1],
  [0.004, 1],
  [0.5, 35],
  [1, 70],
  [-0.3, 21],
])("caps the link's pixel width at openLCA's rule for fraction %d", (fraction, expected) => {
  expect(linkWidth(fraction)).toBe(expected)
})

it('keeps the sign of a credited node and weights its link by magnitude', () => {
  const credited = { ...tree, children: tree.children.map((child, i) => (i === 0 ? { ...child, score: -1.5 } : child)) }
  const { nodes, links } = sankeyFromTree(credited)
  expect(nodes.find((n) => n.id === 'root/0')?.score).toBe(-1.5)
  expect(links.find((l) => l.target === 'root/0')?.value).toBe(1.5)
})
