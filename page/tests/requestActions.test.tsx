import { screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { renderAt } from './render'
import byPath from './fixtures/contributions_path.json'
import byProcess from './fixtures/contributions_process.json'
import databases from './fixtures/databases.json'
import impactMonteCarlo from './fixtures/impact_monte_carlo.json'
import inventory from './fixtures/inventory.json'
import log from './fixtures/log.json'
import requests from './fixtures/requests.json'
import run from './fixtures/run.json'
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
      log: vi.fn(async () => log),
      requests: vi.fn(async () => requests),
      run: vi.fn(async () => run),
      vocabulary: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      impact: vi.fn(async () => impactMonteCarlo),
      contributions: vi.fn(async (_id: string, body: { by: string }) => (body.by === 'path' ? byPath : byProcess)),
      inventory: vi.fn(async () => inventory),
    },
  }
})

const id = system.value.id
const search = `?impact_method=${encodeURIComponent(impactMonteCarlo.value.scores[0].method.impact_method)}`

it.each([
  [`/systems/${id}/results/general${search}`, ['General information', 'Top 5 direct contributions to impact category results - overview']],
  [`/systems/${id}/results/inventory${search}`, ['Inputs', 'Outputs']],
  [`/systems/${id}/results/processes${search}`, ['Process contributions']],
  [`/systems/${id}/results/tree${search}`, ['Contribution tree']],
  [`/systems/${id}/results/sankey${search}`, ['Sankey diagram', 'Sankey nodes']],
  [`/systems/${id}/log`, ['Entries']],
  [`/systems/${id}/requests`, ['Requests']],
  [`/systems/${id}/simulations/${run.value.id}`, ['Settings', 'Progress', 'Results']],
])('%s carries a Request action naming the product system on each section', async (address, titles) => {
  renderAt(address, <App router={false} />)
  for (const title of titles) {
    const heading = await waitFor(() => screen.getByRole('button', { name: title }))
    const section = heading.closest('section')!
    within(section).getAllByRole('button', { name: 'Request' })[0].click()
    expect(useRequestDialog.getState().target).toEqual({ systemId: id, entity: 'product_system', entityId: id })
    useRequestDialog.getState().close()
  }
})
