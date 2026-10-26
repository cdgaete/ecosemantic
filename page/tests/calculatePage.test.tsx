import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { App, Screens } from '@/App'
import { api, ApiError } from '@/api/client'
import type { SystemRead } from '@/api/types'
import { useUi } from '@/store/ui'
import databases from './fixtures/databases.json'
import run from './fixtures/run.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import families from './fixtures/vocabulary_impact_methods.json'
import calculations from './fixtures/calculations.json'
import impact from './fixtures/impact.json'
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
      vocabulary: vi.fn(async () => families),
      searchMethods: vi.fn(async () => ({ items: [], has_more: false, next_cursor: null, hint: null, view_url: null })),
      startRun: vi.fn(async () => run),
      run: vi.fn(async () => run),
      calculations: vi.fn(async () => ({ value: [] })),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => ({ value: { by: 'process', hotspots: [], credit_loops: [], linked_credit_loops: [] }, hint: null, view_url: null })),
    },
  }
})

const id = system.value.id
const family = families.value[0].value

beforeEach(() => vi.clearAllMocks())

async function simulationOf(chosenFamily: string): Promise<void> {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Monte Carlo simulation')).toBeInTheDocument())
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  await waitFor(() => expect(screen.getByLabelText('Family').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Family'), { target: { value: chosenFamily } })
}

it('keeps a long family or category from widening the panel', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  expect(await screen.findByLabelText('Family')).toHaveClass('max-w-full')
  expect(screen.getByLabelText('Category')).toHaveClass('max-w-full')
})

it('offers the variants for an impact result and the stop rule for a simulation', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('Variants')).toBeInTheDocument())
  expect(screen.queryByLabelText('n_max')).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  expect(screen.queryByText('Variants')).not.toBeInTheDocument()
  expect(screen.getByLabelText('n_max')).toBeInTheDocument()
  expect(screen.getByLabelText('Uncertainty in')).toBeInTheDocument()
})

it('starts a simulation with the stop rule and the scope, and opens its editor', async () => {
  await simulationOf(family)
  fireEvent.change(screen.getByLabelText('Uncertainty in'), { target: { value: 'biosphere_only' } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() =>
    expect(api.startRun).toHaveBeenCalledWith(id, {
      impact_method: family,
      monte_carlo: { n_min: 30, n_max: 200, rel_se_target: 0.05, seed: 12345, scope: 'biosphere_only' },
    }),
  )
  await waitFor(() => expect(screen.getByText(`Monte Carlo Simulation – ${system.value.name}`)).toBeInTheDocument())
})

it('keeps a refusal in the dialog with a link to the simulation that holds the slot', async () => {
  const message = 'run r-open is running; one run at a time'
  vi.mocked(api.startRun).mockRejectedValueOnce(new ApiError(409, { error: 'conflict', message, details: { run_id: 'r-open', product_system_id: 's-other' } }))
  await simulationOf(family)
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(screen.getByText(message)).toBeInTheDocument())
  expect(screen.getByRole('link', { name: 'Open that simulation' }).getAttribute('href')).toContain('/systems/s-other/simulations/r-open')
})

it('states the target amount in the reference process the system names, and demands it', async () => {
  vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, reference_process: 'frame' } } as SystemRead)
  // App's own client already holds the system read above; Screens reads through a fresh one
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByText('kilogram of frame')).toBeInTheDocument())
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  await waitFor(() => expect(screen.getByLabelText('Family').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Family'), { target: { value: family } })
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.startRun).toHaveBeenCalled())
  expect(vi.mocked(api.startRun).mock.calls[0][1].demand).toEqual([{ ref: { kind: 'foreground', code: 'frame' }, amount: 2 }])
})

it('starts on the family of the latest calculation that named one, under a tab of its own', async () => {
  const named = { ...calculations.value[0], arguments: { product_system_id: id, impact_method: family } }
  vi.mocked(api.calculations).mockResolvedValueOnce({ value: [named] } as Awaited<ReturnType<typeof api.calculations>>)
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Family')).toHaveValue(family))
  expect(useUi.getState().details?.id).toBe(`calculate:${id}`)
})

it('marks the impact a person calculates as started, and not the same result loaded again', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Family').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Family'), { target: { value: family } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls.map((call) => call[2])).toEqual([true])
  expect(useUi.getState().startedImpact).toBeNull()
  cleanup()
  renderAt(`/systems/${id}/results/impact?impact_method=${encodeURIComponent(family)}`, <Screens />)
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(2))
  expect(vi.mocked(api.impact).mock.calls[1][2]).toBe(false)
})

it('names a category that has no indicator in the category list without a separator', async () => {
  const bare = { id: 'm_bare', impact_category: 'water use', impact_method: 'aware', indicator: '', spec: 'fixture > aware > water use', tuple: ['fixture', 'aware', 'water use'], unit: 'm3' }
  vi.mocked(api.searchMethods).mockResolvedValue({ items: [bare], has_more: false, next_cursor: null, hint: null, view_url: null })
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  fireEvent.click(await screen.findByLabelText('One category'))
  fireEvent.change(screen.getByPlaceholderText('search…'), { target: { value: 'water' } })
  await waitFor(() => expect(screen.getByLabelText('Category').querySelectorAll('option').length).toBe(2))
  expect(screen.getByLabelText('Category').querySelectorAll('option')[1].textContent).toBe('aware › water use [m3]')
})
