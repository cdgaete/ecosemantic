import { screen, waitFor } from '@testing-library/react'
import { App } from '@/App'
import { renderAt } from './render'
import byProcess from './fixtures/contributions_process.json'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'

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
      vocabulary: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      impact: vi.fn(async () => ({ ...impact, hint: 'the impact hint' })),
      contributions: vi.fn(async () => ({ ...byProcess, hint: 'the contributions hint' })),
      inventory: vi.fn(async () => ({ ...inventory, hint: 'the inventory hint' })),
    },
  }
})

const search = `?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`

it("shows the impact answer's hint under the impact table", async () => {
  renderAt(`/systems/${system.value.id}/results/impact${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('the impact hint')).toBeInTheDocument())
})

it("shows the contributions answer's hint under the process results table", async () => {
  renderAt(`/systems/${system.value.id}/results/processes${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('the contributions hint')).toBeInTheDocument())
})

it("shows the inventory listing's hint on its page", async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('the inventory hint')).toBeInTheDocument())
})
