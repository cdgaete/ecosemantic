import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api, ApiError } from '@/api/client'
import type { Answer, Run } from '@/api/types'
import { categoryLabel, formatAmount, methodById, shortHash } from '@/lib/format'
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
  // the recorded run fixed n at 6 over the full scope, and a fixed count holds no category
  expect(field('Iterations')).toBe('6, fixed')
  expect(field('Uncertainty in')).toBe('all exchanges')
  expect(field('Status')).toBe('done')
  expect(screen.getByText('6 iterations, ran its stated count')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /6 samples/ })).toBeInTheDocument()
  // the synthetic background carries two normals wider than their amounts
  expect(screen.getByText('2 background normal distributions held at their amount, their standard deviation exceeding it.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
})

it('opens on what it drew, ahead of how the run stopped', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(
    answer({
      result: {
        ...result,
        drawn: {
          parameters: { there: 3, carried: 3, drawn: 3, held: 0 },
          foreground: { there: 9, carried: 4, drawn: 4, held: 0 },
          background: { there: 20, carried: 12, drawn: 10, held: 2 },
        },
      },
    }),
  )
  open()
  await waitFor(() => expect(screen.getByText('Drawn: 3 parameters, 4 of 9 foreground exchanges, 10 of 20 background exchanges')).toBeInTheDocument())
  expect(screen.getByText('2 background normal distributions held at their amount, their standard deviation exceeding it.')).toBeInTheDocument()
  const drawn = screen.getByText(/^Drawn:/)
  const stopped = screen.getByText(/^6 iterations/)
  expect(drawn.compareDocumentPosition(stopped) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('groups a count of a thousand or more as every other number on the page is grouped', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(
    answer({
      result: {
        ...result,
        drawn: {
          parameters: { there: 1234, carried: 1234, drawn: 1234, held: 0 },
          foreground: { there: 2147, carried: 2147, drawn: 2147, held: 0 },
          background: { there: 154845, carried: 129184, drawn: 129184, held: 1500 },
        },
      },
    }),
  )
  open()
  await waitFor(() =>
    expect(screen.getByText('Drawn: 1,234 parameters, 2,147 of 2,147 foreground exchanges, 129,184 of 154,845 background exchanges')).toBeInTheDocument(),
  )
  expect(screen.getByText('1,500 background normal distributions held at their amount, their standard deviation exceeding it.')).toBeInTheDocument()
})

it("names the median as what the stop rule judges and the table leads with", async () => {
  vi.mocked(api.run).mockResolvedValueOnce(answer({ config: { ...done.value.config, n: null } }))
  open()
  await waitFor(() => expect(field('Iterations')).toBe("1 to 200, until every median's relative standard error is under 0.05"))
  expect(field('Worst median relative SE')).toMatch(/, target 0.05$/)
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
  expect(headers).toEqual(['Impact category', 'n', 'Median', 'Median 95 % low', 'Median 95 % high', 'Median relative SE', '2.5 – 97.5 %', 'Mean', 'Unit'])
})

it('folds the figures a narrow panel cannot hold under the category, keeping the interval in the row', async () => {
  open()
  const table = await waitFor(() => screen.getByRole('table'))
  for (const name of ['n', 'Median 95 % low', 'Median 95 % high', 'Median relative SE', 'Mean', 'Unit'])
    expect(within(table).getByRole('columnheader', { name })).toHaveClass('hidden', '@3xl:table-cell')
  for (const name of ['Impact category', 'Median', '2.5 – 97.5 %'])
    expect(within(table).getByRole('columnheader', { name })).not.toHaveClass('hidden')
  const first = done.value.result!.categories[0]
  const summary = first.summary
  const folded = [...within(table).getAllByRole('row')[1].querySelectorAll('td')[0].children].filter((el) => el.className.includes('@3xl:hidden'))
  expect(folded.map((el) => el.textContent?.trim())).toEqual([
    `n: ${summary.n}`,
    `Median 95 % low: ${formatAmount(summary.median_ci95![0])}`,
    `Median 95 % high: ${formatAmount(summary.median_ci95![1])}`,
    `Median relative SE: ${formatAmount(summary.rel_se!)}`,
    `Mean: ${formatAmount(summary.mean)}`,
    `Unit: ${methodById(done.value.methods, first.method_id).unit}`,
  ])
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
  await waitFor(() => expect(screen.getByText(/, stopped on request$/)).toBeInTheDocument())
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
  const [firstMethod] = done.value.methods
  const otherMethod = { ...firstMethod, id: 'm_gwp20', indicator: 'GWP20' }
  const other = { ...first, method_id: 'm_gwp20' }
  vi.mocked(api.run).mockResolvedValueOnce(answer({ methods: [firstMethod, otherMethod], result: { ...result, categories: [first, other] } }))
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

it('names one background normal held at its amount, and says nothing of none', async () => {
  const result = done.value.result!
  const held = (count: number) => ({ ...result, drawn: { ...result.drawn, background: { ...result.drawn.background, held: count } } })
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: held(1) }))
  const view = open()
  await waitFor(() => expect(screen.getByText('1 background normal distribution held at its amount, its standard deviation exceeding it.')).toBeInTheDocument())
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: held(0) }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/held at (its|their) amount/)).not.toBeInTheDocument()
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
  await waitFor(() => expect(screen.getByText(/^1 iteration, stopped on request/)).toBeInTheDocument())
})

it('counts the iterations kept of those taken when it dropped draws', async () => {
  const result = done.value.result!
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, dropped_draws: [1, 3], dropped_loops: [['widget']], dropped_background: [] } }))
  open()
  await waitFor(() => expect(screen.getByText(/^6 of 8 iterations kept, ran its stated count$/)).toBeInTheDocument())
})

it('names the category that held the run longest, and none where no category held it', async () => {
  const result = done.value.result!
  const [firstMethod] = done.value.methods
  const water = { ...firstMethod, id: 'm_water', impact_category: 'water use', indicator: 'm3' }
  const view = open()
  await waitFor(() => expect(screen.getByText('6 iterations, ran its stated count')).toBeInTheDocument())
  expect(screen.queryByText(/held longest by/)).not.toBeInTheDocument()
  view.unmount()
  vi.mocked(api.run).mockResolvedValueOnce(answer({ methods: [firstMethod, water], result: { ...result, gating_method: 'm_water' } }))
  open()
  await waitFor(() => expect(screen.getByText('6 iterations, ran its stated count, held longest by water use · m3')).toBeInTheDocument())
})

it("shows each weighting set's total as a row after the categories, with what it rests on", async () => {
  const result = done.value.result!
  const [firstMethod] = done.value.methods
  const notice = 'A weighted total rests on value choices, as this answer words it.'
  const totals = [
    {
      impact_method: firstMethod.impact_method,
      weighting_set: 'Total (water resources, evaporated)',
      position: 0,
      unit: 'UBP',
      categories: [firstMethod.id],
      normalised_by_zero: [],
      summary: { ...result.categories[0].summary, median: 987.65 },
      samples: null,
      histogram: null,
      reason: null,
      value_choices: notice,
    },
    { impact_method: firstMethod.impact_method, weighting_set: null, position: 1, unit: null, categories: [], normalised_by_zero: [], summary: null, samples: null, histogram: null, reason: 'weights no category', value_choices: notice },
  ]
  vi.mocked(api.run).mockResolvedValueOnce(answer({ result: { ...result, totals } }))
  open()
  await waitFor(() => expect(screen.getByText('Total (water resources, evaporated)')).toBeInTheDocument())
  const table = screen.getByRole('table')
  const named = within(table).getByText('Total (water resources, evaporated)').closest('tr')!
  const unnamed = within(table).getByText('Unnamed set 2').closest('tr')!
  expect(within(named).getByText(formatAmount(987.65))).toBeInTheDocument()
  expect(within(unnamed).getByText('weights no category')).toBeInTheDocument()
  expect(screen.getByText(notice)).toBeInTheDocument()
  const last = within(table).getByText(categoryLabel(methodById(done.value.methods, result.categories[0].method_id))).closest('tr')!
  expect(last.compareDocumentPosition(named) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(named.compareDocumentPosition(unnamed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('draws no total row and no value-choice notice where no weighting set gives a total', async () => {
  open()
  await waitFor(() => expect(screen.getByText(/^6 iterations/)).toBeInTheDocument())
  expect(screen.queryByText(/^Unnamed set/)).not.toBeInTheDocument()
  expect(screen.queryByText(/value choices/)).not.toBeInTheDocument()
})

it('names the category met as constant and the one left out of the stop rule, and no other line', async () => {
  const result = done.value.result!
  const [firstMethod] = done.value.methods
  const water = { ...firstMethod, id: 'm_water', impact_category: 'water use', indicator: 'm3' }
  vi.mocked(api.run).mockResolvedValueOnce(
    answer({
      methods: [firstMethod, water],
      result: { ...result, gating_method: null, constant: ['m_water'], indistinguishable_from_zero: [firstMethod.id] },
    }),
  )
  open()
  await waitFor(() => expect(screen.getByText('Met as constant, every draw equal: water use · m3.')).toBeInTheDocument())
  expect(screen.getByText('Left out of the stop rule, their median indistinguishable from zero: climate change · GWP100.')).toBeInTheDocument()
  expect(screen.getByText('6 iterations, ran its stated count')).toBeInTheDocument()
  expect(screen.queryByText(/held longest by/)).not.toBeInTheDocument()
})
