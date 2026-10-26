import { screen, within } from '@testing-library/react'
import { App } from '@/App'
import databases from './fixtures/databases.json'
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
      runs: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
    },
  }
})

it('sends a system with no simulation to the Monte Carlo setup', async () => {
  renderAt(`/systems/${system.value.id}/simulations`, <App router={false} />)
  const empty = await screen.findByText(/No simulation yet/)
  const start = within(empty).getByRole('link', { name: 'Monte Carlo simulation…' })
  expect(start.getAttribute('href')).toContain(`/systems/${system.value.id}/results/setup?kind=simulation`)
})
