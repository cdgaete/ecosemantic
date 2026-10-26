import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App, Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, Call, ImpactResult, SystemRead, Value } from '@/api/types'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import validation from './fixtures/validation.json'
import recordedImpact from './fixtures/impact.json'
import byProcess from './fixtures/contributions_process.json'
import calculations from './fixtures/calculations.json'

const impact = recordedImpact as Answer<ImpactResult>
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
      contributions: vi.fn(async () => byProcess),
      calculations: vi.fn(async () => calculations),
    },
  }
})

const recorded = calculations.value[0] as Call
const callOn = (patch: Partial<Call>): Value<Call[]> => ({ value: [{ ...recorded, product_system_id: system.value.id, ...patch }] })

it('shows the impact analysis with a row per category', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Impact analysis: ${impact.value.scores[0].method.impact_method}`)).toBeInTheDocument())
  // The title renders from the URL's impact_method param before the impact query settles, so the
  // category cells (which need the fetched scores) need their own wait.
  await waitFor(() => {
    for (const score of impact.value.scores) expect(screen.getByText(score.method.impact_category)).toBeInTheDocument()
  })
  expect(screen.getByText('Sub-group by:')).toBeInTheDocument()
})

it('lists the top 5 contributions in a table beside the chart', async () => {
  renderAt(`/systems/${system.value.id}/results/general?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  const heading = await screen.findByText('Top 5 direct contributions to impact category results - overview')
  const table = await waitFor(() => within(heading.closest('section')!).getByRole('table'))
  for (const p of byProcess.value.processes) expect(within(table).getByText(new RegExp(p.name))).toBeInTheDocument()
})

it('demands the reference process the system names', async () => {
  vi.mocked(api.impact).mockClear()
  vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, reference_process: 'frame' } } as SystemRead)
  // App's own client already holds the system read above; Screens reads through a fresh one
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}&amount=2`, <Screens />)
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  const body = vi.mocked(api.impact).mock.calls[0][1]
  expect(body.demand?.[0].ref).toEqual({ kind: 'foreground', code: 'frame' })
})

it('opens a recorded calculation with the arguments it was made with, and says it also ran a Monte Carlo', async () => {
  vi.mocked(api.impact).mockClear()
  vi.mocked(api.system).mockResolvedValue(system as SystemRead)
  const demand = [{ ref: { kind: 'foreground', code: 'frame' }, amount: 2 }]
  vi.mocked(api.calculations).mockResolvedValue(callOn({ arguments: { product_system_id: system.value.id, method_id: 'm_x', variants: ['heavy'], demand, monte_carlo: { n: 10 } } }))
  renderAt(`/systems/${system.value.id}/results/general?call=${recorded.id}`, <Screens />)
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls[0][1]).toEqual({ method_id: 'm_x', variants: ['heavy'], demand })
  expect(await screen.findByText(/also ran a Monte Carlo simulation/)).toBeInTheDocument()
  expect(screen.getByText(/2 kilogram of/)).toBeInTheDocument()
})

it('names both hashes when the calculation was recorded on an earlier version', async () => {
  vi.mocked(api.system).mockResolvedValue(system as SystemRead)
  vi.mocked(api.calculations).mockResolvedValue(callOn({ at_hash: 'feedbeef0000aaaa' }))
  renderAt(`/systems/${system.value.id}/results/impact?call=${recorded.id}`, <Screens />)
  expect(await screen.findByText(/Recorded on feedbe…aaaa; computed here on the current model/)).toBeInTheDocument()
})

it('says when no calculation of that id is recorded', async () => {
  vi.mocked(api.calculations).mockResolvedValue({ value: [] })
  renderAt(`/systems/${system.value.id}/results/impact?call=nothing`, <Screens />)
  expect(await screen.findByText('No calculation nothing is recorded for this product system.')).toBeInTheDocument()
})

it('opens a recorded calculation whose demand holds several items, and names each of them', async () => {
  vi.mocked(api.impact).mockClear()
  vi.mocked(api.system).mockResolvedValue(system as SystemRead)
  const demand = [
    { ref: { kind: 'foreground', code: 'frame' }, amount: 2 },
    { ref: { kind: 'foreground', code: 'widget' }, amount: 3 },
  ]
  vi.mocked(api.calculations).mockResolvedValue(callOn({ arguments: { product_system_id: system.value.id, method_id: 'm_x', demand } }))
  renderAt(`/systems/${system.value.id}/results/general?call=${recorded.id}`, <Screens />)
  await waitFor(() => expect(api.impact).toHaveBeenCalled())
  expect(vi.mocked(api.impact).mock.calls[0][1]).toEqual({ method_id: 'm_x', variants: [], demand })
  expect(await screen.findByText('2 kilogram of frame, 3 unit of widget')).toBeInTheDocument()
})

it('names the method of a category that has no indicator without a separator', async () => {
  const [score] = impact.value.scores
  const bare = { ...score, method: { ...score.method, indicator: '' } }
  vi.mocked(api.impact).mockResolvedValue({ ...impact, value: { ...impact.value, scores: [bare] } } as typeof impact)
  // an amount of its own keys a query no earlier test cached
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(score.method.impact_method)}&amount=3`, <App router={false} />)
  const row = (await screen.findByText(score.method.impact_category)).closest('tr')!
  expect(within(row).getByText(score.method.impact_method, { selector: 'td' }).textContent).toBe(score.method.impact_method)
  vi.mocked(api.impact).mockResolvedValue(impact)
})
