import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api, ApiError } from '@/api/client'
import type { Answer, Run } from '@/api/types'
import { shortHash } from '@/lib/format'
import databases from './fixtures/databases.json'
import run from './fixtures/run.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import { FakeSource } from './fakeSource'
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
      run: vi.fn(async () => run),
      cancelRun: vi.fn(async () => run),
    },
  }
})

const done = run as unknown as Answer<Run>
const id = system.value.id
const address = `/systems/${id}/simulations/${done.value.id}`

function answer(patch: Partial<Run>): Answer<Run> {
  return { ...done, value: { ...done.value, ...patch } }
}

const running = answer({ status: 'running', open: true, result: null, finished_at: null, progress: { iterations: 7, worst_rel_se: 0.2 } })

function field(label: string): string | null | undefined {
  return screen.getByText(label).nextElementSibling?.textContent
}

// every test reads the same run, so each renders through a fresh query client rather than App's
function open() {
  return renderAt(address, <Screens />)
}

beforeEach(() => {
  vi.clearAllMocks()
  FakeSource.instances = []
  vi.stubGlobal('EventSource', FakeSource)
})
afterEach(() => vi.unstubAllGlobals())

it('shows the settings, the progress and the results of a finished simulation', async () => {
  open()
  await waitFor(() => expect(screen.getByText(`Monte Carlo Simulation – ${system.value.name}`)).toBeInTheDocument())
  // the recorded run fixed n at 6 over the full scope
  expect(field('Iterations')).toBe('6, fixed')
  expect(field('Uncertainty in')).toBe('all exchanges')
  expect(field('Status')).toBe('done')
  // the recorded gating method is ('climate change', 'GWP100')
  expect(screen.getByText('6 iterations, ran its stated count, gated on climate change · GWP100')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /6 samples/ })).toBeInTheDocument()
  // the synthetic background carries two normals wider than their amounts
  expect(screen.getByText('2 background normal distributions were sampled at their amount, as their standard deviation exceeds it.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
})

it("names the median as what the stop rule judges and the table leads with", async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ config: { ...done.value.config, n: null } }))
  open()
  await waitFor(() => expect(field('Iterations')).toBe("1 to 200, until every median's relative standard error is under 0.05"))
  expect(field('Worst median relative SE')).toMatch(/, target 0.05$/)
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
  expect(headers).toEqual(['Impact category', 'n', 'Median', 'Median 95 % low', 'Median 95 % high', 'Median relative SE', '2.5th pct', '97.5th pct', 'Mean', 'Unit'])
})

it("names the demanded process by its name, as the system holds it", async () => {
  open()
  await waitFor(() => expect(screen.getByText(`Monte Carlo Simulation – ${system.value.name}`)).toBeInTheDocument())
  expect(field('Demand')).toBe('widget assembly × 1')
})

it('asks a running simulation to stop and says so while it stops', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(running)
  vi.mocked(api.cancelRun).mockResolvedValueOnce(answer({ ...running.value, cancel_requested: true }))
  open()
  const button = await waitFor(() => screen.getByRole('button', { name: 'Cancel' }))
  expect(field('Iterations taken')).toBe('7')
  fireEvent.click(button)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Stopping…' })).toBeDisabled())
  expect(api.cancelRun).toHaveBeenCalledWith(done.value.id)
  expect(screen.getByText('The results appear when the simulation finishes.')).toBeInTheDocument()
})

it('keeps the results of a cancelled simulation and says it was stopped', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ status: 'cancelled', cancel_requested: true, result: { ...done.value.result!, stopped: 'cancelled' } }))
  open()
  await waitFor(() => expect(screen.getByText(/, stopped on request, gated on /)).toBeInTheDocument())
})

it('shows why a failed simulation has no result', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ status: 'failed', result: null, error: { error: 'failed', message: 'the worker for run x did not finish', details: {} } }))
  open()
  await waitFor(() => expect(screen.getByText('the worker for run x did not finish')).toBeInTheDocument())
  expect(screen.getByText('This simulation holds no result.')).toBeInTheDocument()
})

it('notes a model that has moved since the simulation started, linking to the state it ran on', async () => {
  const earlier = 'f'.repeat(64)
  vi.mocked(api.run).mockResolvedValueOnce(answer({ at_hash: earlier }))
  open()
  await waitFor(() => expect(screen.getByText('The model has changed since this simulation started.')).toBeInTheDocument())
  expect(screen.getByRole('link', { name: shortHash(earlier) }).getAttribute('href')).toContain(`/systems/${id}/versions/${earlier}`)
})

it("shows an unknown run's error in the editor", async () => {
  vi.mocked(api.run).mockRejectedValueOnce(new ApiError(404, { error: 'not_found', message: 'no run x', details: {} }))
  open()
  await waitFor(() => expect(screen.getByText('no run x')).toBeInTheDocument())
})

it('redraws on a run event without reading the run again', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(running)
  open()
  await waitFor(() => expect(field('Iterations taken')).toBe('7'))
  const source = FakeSource.instances[0]
  act(() => source.emit('run', { kind: 'run', product_system_id: id, entry: null, request: null, run: { ...running.value, progress: { iterations: 12, worst_rel_se: 0.1 } } }))
  await waitFor(() => expect(field('Iterations taken')).toBe('12'))
  expect(api.run).toHaveBeenCalledTimes(1)
})

it('tells apart two categories that share a name by their indicator', async () => {
  const result = done.value.result!
  const [first] = result.categories
  const other = { ...first, method: { ...first.method, id: 'm_gwp20', indicator: 'GWP20' } }
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, categories: [first, other] } }))
  open()
  const select = await waitFor(() => screen.getByLabelText('Impact category'))
  expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual(['climate change · GWP100', 'climate change · GWP20'])
  const table = screen.getByRole('table')
  expect(within(table).getByText('climate change · GWP100')).toBeInTheDocument()
  expect(within(table).getByText('climate change · GWP20')).toBeInTheDocument()
})

it('lets the category select shrink within the panel rather than widen it past a long name', async () => {
  open()
  const select = await waitFor(() => screen.getByLabelText('Impact category'))
  expect(select.className).toContain('min-w-0')
  expect(select.className).toContain('flex-1')
})

it('names one background normal sampled at its amount, and says nothing of none', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, normals_at_amount: 1 } }))
  const view = open()
  await waitFor(() => expect(screen.getByText('1 background normal distribution was sampled at its amount, as its standard deviation exceeds it.')).toBeInTheDocument())
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, normals_at_amount: 0 } }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/sampled at (its|their) amount/)).not.toBeInTheDocument()
})

it('names each loop holding a credit beside the results, and says nothing of none', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, credit_loops: [['frame', 'widget']] } }))
  const view = open()
  await waitFor(() => expect(screen.getByText('The loop through frame, widget holds a credit; whether it delivers what it makes is not checked.')).toBeInTheDocument())
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, credit_loops: [] } }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/holds a credit/)).not.toBeInTheDocument()
})

it('names each exchange that runs a treatment backwards while the simulation runs, and says nothing of none', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ ...running.value, treatments_run_backwards: ['widget · steel at 0.5'] }))
  const view = open()
  await waitFor(() => expect(screen.getByText('widget · steel at 0.5 sends a positive amount to a treatment, which runs it backwards and counts its emissions as credits; waste goes to a treatment as a negative input.')).toBeInTheDocument())
  expect(screen.getByText('The results appear when the simulation finishes.')).toBeInTheDocument()
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ treatments_run_backwards: [] }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/runs it backwards/)).not.toBeInTheDocument()
})

it('counts the draws it dropped and names the loops that made no more than they used', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, dropped_draws: [1, 3], dropped_loops: [['widget'], ['frame', 'widget']], dropped_background: [] } }))
  const view = open()
  await waitFor(() => expect(screen.getByText('2 of 8 draws were dropped: in each, a process or loop made no more than it used (widget; frame, widget).')).toBeInTheDocument())
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, dropped_draws: [], dropped_loops: [], dropped_background: [] } }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/were dropped/)).not.toBeInTheDocument()
})

it('names the background process a dropped draw failed on', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, dropped_draws: [0], dropped_loops: [], dropped_background: ['pellet production [GLO]'] } }))
  open()
  await waitFor(() => expect(screen.getByText('1 of 7 draws were dropped: in each, a process or loop made no more than it used (in the background, pellet production [GLO]).')).toBeInTheDocument())
})

it('counts a single iteration in the singular', async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ status: 'cancelled', cancel_requested: true, result: { ...done.value.result!, n: 1, stopped: 'cancelled' } }))
  open()
  await waitFor(() => expect(screen.getByText(/^1 iteration, stopped on request, gated on /)).toBeInTheDocument())
})

it('counts the iterations kept of those taken when it dropped draws', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, dropped_draws: [1, 3], dropped_loops: [['widget']], dropped_background: [] } }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 of 8 iterations kept, ran its stated count, gated on /)).toBeInTheDocument())
})
