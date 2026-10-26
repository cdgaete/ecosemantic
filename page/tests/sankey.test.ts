import type { ContributionResult } from '@/api/types'
import { linkWidth, sankeyFromTree } from '@/editors/results/figures/sankey'
import byPath from './fixtures/contributions_path.json'

const tree = (byPath.value as ContributionResult).root!

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
