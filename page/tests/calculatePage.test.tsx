import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { App, Screens } from '@/App'
import { api, ApiError } from '@/api/client'
import type { Answer, MonteCarloConfig, SystemRead } from '@/api/types'
import { useUi } from '@/store/ui'
import databases from './fixtures/databases.json'
import run from './fixtures/run.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import families from './fixtures/vocabulary_impact_methods.json'
import calculations from './fixtures/calculations.json'
import impact from './fixtures/impact.json'
import monteCarlo from './fixtures/monte_carlo.json'
import tree from './fixtures/explorer_methods.json'
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
      vocabulary: vi.fn(async () => ({ ...families, value: [...families.value, { value: 'aware', detail: '1 method' }] })),
      methodTree: vi.fn(async () => methodTree),
      searchMethods: vi.fn(async () => ({ items: [], has_more: false, next_cursor: null, hint: null, view_url: null })),
      startRun: vi.fn(async () => run),
      monteCarlo: vi.fn(async () => defaults),
      run: vi.fn(async () => run),
      calculations: vi.fn(async () => ({ value: [] })),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => ({ value: { by: 'process', hotspots: [], credit_loops: [], linked_credit_loops: [] }, hint: null, view_url: null })),
    },
  }
})

const id = system.value.id

const gwp = tree.value[0].categories[0].indicators[0]
const fossil = { ...gwp, id: 'm_fossil', impact_category: 'climate change: fossil', spec: 'fixture > gwp > climate change: fossil > GWP100', tuple: ['fixture', 'gwp', 'climate change: fossil', 'GWP100'] }
const water = tree.value[1].categories[0].indicators[0]
const bare = { ...water, id: 'm_bare', impact_category: 'water use', impact_method: 'aware', indicator: 'water use', spec: 'fixture > aware > water use > water use', tuple: ['fixture', 'aware', 'water use', 'water use'] }
const methodTree = {
  value: [
    { name: 'gwp', categories: [{ name: 'climate change', indicators: [gwp] }, { name: 'climate change: fossil', indicators: [fossil] }] },
    tree.value[1],
    { name: 'aware', categories: [{ name: 'water use', indicators: [bare] }] },
  ],
  hint: null,
  view_url: null,
}
const family = families.value[0].value
const defaults = monteCarlo as unknown as Answer<MonteCarloConfig>

beforeEach(() => {
  vi.clearAllMocks()
  useUi.setState({ canvasSystemId: null, canvasVariant: null })
})

function withCase(name: string): void {
  vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, cases: [...system.value.cases, { ...system.value.cases[0], name }] } } as SystemRead)
}

async function simulationOf(chosenFamily: string): Promise<void> {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Monte Carlo simulation')).toBeInTheDocument())
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: chosenFamily } })
}

it('keeps a long family or category from widening the panel', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  expect(await screen.findByLabelText('Method')).toHaveClass('max-w-full')
  expect(screen.getByLabelText('Category')).toHaveClass('max-w-full')
})

it('offers the variants for an impact result and the stop rule for a simulation', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('Variants')).toBeInTheDocument())
  expect(screen.queryByLabelText('Most draws')).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  expect(screen.queryByText('Variants')).not.toBeInTheDocument()
  expect(await screen.findByLabelText('Most draws')).toBeInTheDocument()
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

it('starts the simulation form from the defaults the server answers', async () => {
  vi.mocked(api.monteCarlo).mockResolvedValueOnce({ value: { n_min: 5, n_max: 40, rel_se_target: 0.01, seed: 7, scope: 'biosphere_only', n: null }, hint: null, view_url: null })
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Monte Carlo simulation')).toBeInTheDocument())
  fireEvent.click(screen.getByLabelText('Monte Carlo simulation'))
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: family } })
  expect(await screen.findByLabelText('Fewest draws')).toHaveValue(5)
  expect(screen.getByLabelText('Most draws')).toHaveValue(40)
  expect(screen.getByLabelText('Target precision')).toHaveValue(0.01)
  expect(screen.getByLabelText('Seed')).toHaveValue(7)
  expect(screen.getByLabelText('Uncertainty in')).toHaveValue('biosphere_only')
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() =>
    expect(api.startRun).toHaveBeenCalledWith(id, {
      impact_method: family,
      monte_carlo: { n_min: 5, n_max: 40, rel_se_target: 0.01, seed: 7, scope: 'biosphere_only' },
    }),
  )
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
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: family } })
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.startRun).toHaveBeenCalled())
  expect(vi.mocked(api.startRun).mock.calls[0][1].demand).toEqual([{ ref: { kind: 'foreground', code: 'frame' }, amount: 2 }])
})

it('starts on the family of the latest calculation that named one, under a tab of its own', async () => {
  const named = { ...calculations.value[0], arguments: { product_system_id: id, impact_method: family } }
  vi.mocked(api.calculations).mockResolvedValueOnce({ value: [named] } as Awaited<ReturnType<typeof api.calculations>>)
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method')).toHaveValue(family))
  expect(useUi.getState().details?.id).toBe(`calculate:${id}`)
})

it('opens on the method and the category of the latest calculation', async () => {
  const one = { ...calculations.value[0], arguments: { product_system_id: id, method_id: fossil.id } }
  const earlier = { ...calculations.value[0], id: 'earlier', arguments: { product_system_id: id, impact_method: 'water' } }
  vi.mocked(api.calculations).mockResolvedValueOnce({ value: [one, earlier] } as Awaited<ReturnType<typeof api.calculations>>)
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method')).toHaveValue('gwp'))
  expect(screen.getByLabelText('Category')).toHaveValue(fossil.id)
  expect(screen.getByRole('button', { name: 'Calculate' })).toBeEnabled()
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'water' } })
  expect(screen.getByLabelText('Category')).toHaveValue('')
})

it('opens on all the categories of the method the latest calculation named', async () => {
  const whole = { ...calculations.value[0], arguments: { product_system_id: id, impact_method: 'water' } }
  const earlier = { ...calculations.value[0], id: 'earlier', arguments: { product_system_id: id, method_id: fossil.id } }
  vi.mocked(api.calculations).mockResolvedValueOnce({ value: [whole, earlier] } as Awaited<ReturnType<typeof api.calculations>>)
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method')).toHaveValue('water'))
  expect(screen.getByLabelText('Category')).toHaveValue('')
})

it('marks the impact a person calculates as started, and not the same result loaded again', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: family } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls.map((call) => call[2])).toEqual([true])
  expect(useUi.getState().startedImpact).toBeNull()
  cleanup()
  renderAt(`/systems/${id}/results/impact?impact_method=${encodeURIComponent(family)}`, <Screens />)
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(2))
  expect(vi.mocked(api.impact).mock.calls[1][2]).toBe(false)
})

it('names a category that is its own indicator once in the category list', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'aware' } })
  await waitFor(() => expect(categoryOptions()).toEqual(['All categories', 'water use [m3]']))
})

it('opens the setup form with the case the canvas shows ticked, and calculates it', async () => {
  withCase('PPA solar 60%')
  useUi.setState({ canvasSystemId: id, canvasVariant: 'PPA solar 60%' })
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  expect(screen.getByLabelText('PPA solar 60%')).toBeChecked()
  expect(screen.getByText('The canvas shows case PPA solar 60%; it is ticked below.')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: family } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls[0][1]).toMatchObject({ variants: ['PPA solar 60%'] })
})

it('opens the setup form with nothing ticked while the canvas shows the base values', async () => {
  withCase('PPA solar 60%')
  useUi.setState({ canvasSystemId: id, canvasVariant: null })
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  expect(screen.getByLabelText('PPA solar 60%')).not.toBeChecked()
  expect(screen.getByLabelText(system.value.cases[0].name)).not.toBeChecked()
  expect(screen.queryByText(/The canvas shows/)).not.toBeInTheDocument()
})

it('calculates a case whose name holds a comma', async () => {
  vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, cases: [{ ...system.value.cases[0], name: 'a, b' }] } } as SystemRead)
  renderAt(`/systems/${id}/results/setup`, <Screens />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: family } })
  fireEvent.click(screen.getByLabelText('a, b'))
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls[0][1]).toMatchObject({ variants: ['a, b'] })
})

const categoryOptions = () => Array.from(screen.getByLabelText('Category').querySelectorAll('option')).map((o) => o.textContent)

it('the Monte Carlo fields say what they do', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  fireEvent.click(await screen.findByLabelText('Monte Carlo simulation'))
  const fewest = await screen.findByLabelText('Fewest draws')
  expect(fewest.closest('label')).toHaveAttribute('title', 'n_min')
  expect(screen.getByLabelText('Most draws').closest('label')).toHaveAttribute('title', 'n_max')
  expect(screen.getByLabelText('Target precision').closest('label')).toHaveAttribute('title', 'rel_se_target')
  expect(screen.getByLabelText('Seed').closest('label')).toHaveAttribute('title', 'seed')
  expect(screen.getByLabelText('Uncertainty in').closest('label')).toHaveAttribute('title', 'scope')
})

it('lists the categories of the chosen method, and none before one is chosen', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  expect(screen.getByLabelText('Category')).toBeDisabled()
  expect(categoryOptions()).toEqual(['All categories'])
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'gwp' } })
  await waitFor(() =>
    expect(categoryOptions()).toEqual(['All categories', 'climate change · GWP100 [kg CO2-Eq]', 'climate change: fossil · GWP100 [kg CO2-Eq]']),
  )
  expect(screen.getByLabelText('Category')).toBeEnabled()
  expect(screen.queryByPlaceholderText('search…')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('One category')).not.toBeInTheDocument()
  expect(api.searchMethods).not.toHaveBeenCalled()
})

it('calculates the one category chosen under its method', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  expect(screen.getByRole('button', { name: 'Calculate' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'gwp' } })
  await waitFor(() => expect(categoryOptions()).toHaveLength(3))
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: fossil.id } })
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }))
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  const asked = vi.mocked(api.impact).mock.calls[0][1]
  expect(asked).toMatchObject({ method_id: fossil.id })
  expect(asked).not.toHaveProperty('impact_method')
})

it('returns to all categories when another method is chosen', async () => {
  renderAt(`/systems/${id}/results/setup`, <App router={false} />)
  await waitFor(() => expect(screen.getByLabelText('Method').querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'gwp' } })
  await waitFor(() => expect(categoryOptions()).toHaveLength(3))
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: fossil.id } })
  expect(screen.getByLabelText('Category')).toHaveValue(fossil.id)
  fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'water' } })
  await waitFor(() => expect(categoryOptions()).toEqual(['All categories', 'water use · m3 [m3]']))
  expect(screen.getByLabelText('Category')).toHaveValue('')
})
