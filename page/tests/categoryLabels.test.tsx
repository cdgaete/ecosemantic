import { screen, waitFor } from '@testing-library/react'
import { App } from '@/App'
import byPath from './fixtures/contributions_path.json'
import byProcess from './fixtures/contributions_process.json'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

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
      contributions: vi.fn(async (_id: string, body: { by: string }) => (body.by === 'path' ? byPath : byProcess)),
    },
  }
})

const search = `?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
// the fixture's one method is ('climate change', 'GWP100')
const label = 'climate change · GWP100'

it.each([
  ['processes', 'processes-category'],
  ['tree', 'tree-category'],
  ['sankey', 'sankey-category'],
])('names the indicator in the %s page category selector', async (page, selectId) => {
  renderAt(`/systems/${system.value.id}/results/${page}${search}`, <App router={false} />)
  await waitFor(() => expect(document.getElementById(selectId)?.querySelectorAll('option').length).toBeGreaterThan(0))
  expect(Array.from(document.getElementById(selectId)!.querySelectorAll('option')).map((o) => o.textContent)).toEqual([label])
})

it('names the indicator under the top contributions chart', async () => {
  renderAt(`/systems/${system.value.id}/results/general${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument())
})
