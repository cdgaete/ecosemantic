import { screen, within } from '@testing-library/react'
import type { ContributionResult, TreeNode } from '@/api/types'
import { App } from '@/App'
import { formatAmount } from '@/lib/format'
import { renderAt } from './render'
import databases from './fixtures/databases.json'
import byPath from './fixtures/contributions_path.json'
import impact from './fixtures/impact.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'

const tree = byPath.value as ContributionResult
const credited: TreeNode = { ...tree.root!, children: tree.root!.children.map((child, i) => (i === 0 ? { ...child, score: -1.5, fraction: -0.25 } : child)) }

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      validation: vi.fn(async () => validation),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => ({ ...byPath, value: { ...tree, root: credited } })),
    },
  }
})

it('shows a credited node with its negative score in the node table', async () => {
  renderAt(`/systems/${system.value.id}/results/sankey?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  const heading = await screen.findByText('Sankey nodes')
  const table = within(heading.closest('section')!).getByRole('table')
  const row = within(table).getByText(new RegExp(`^${credited.children[0].name}`)).closest('tr')!
  expect(row.textContent).toContain(formatAmount(-1.5))
})
