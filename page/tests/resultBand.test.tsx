import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { renderInSlots } from './render'
import { layoutAnswer } from './placements'
import { api } from '@/api/client'
import type { Answer, Call, ImpactArguments, ImpactResult, Method, ProductSystem, Score, Value, VariantScores } from '@/api/types'
import { GraphPage } from '@/editors/system/GraphPage'
import { formatAmount, shortHash } from '@/lib/format'
import { useUi } from '@/store/ui'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import calculations from './fixtures/calculations.json'
import recordedImpact from './fixtures/impact.json'
import recordedSplit from './fixtures/contributions_stage.json'

const doc = system.value as ProductSystem
const recorded = calculations.value[0] as unknown as Call
const base = recordedImpact as Answer<ImpactResult>
const split = recordedSplit as unknown as Awaited<ReturnType<typeof api.contributions>>

const water: Method = {
  id: 'm_second',
  tuple: ['fixture', 'aware', 'water use', 'AWARE'],
  spec: 'fixture > aware > water use > AWARE',
  unit: 'm3 eq',
  impact_method: 'aware',
  impact_category: 'water use',
  indicator: 'AWARE',
}

function answer(body: ImpactArguments): Answer<ImpactResult> {
  const family = typeof body.impact_method === 'string'
  const methods = family ? [base.value.methods[0], water] : base.value.methods
  const scores: Score[] = family ? [base.value.scores[0], { method_id: water.id, unit: water.unit, value: 0.42 }] : base.value.scores
  const variants: VariantScores[] = (body.variants ?? []).map((name) => ({
    name,
    scores: scores.map((score) => ({ ...score, value: name === 'heavy' ? (score.method_id === water.id ? 0.6 : 5.548) : score.value })),
    deltas: scores.map(() => 0),
    totals: [],
    total_deltas: [],
    credit_loops: [],
    linked_credit_loops: [],
    treatments_run_backwards: [],
    uncertainty: null,
    paired_deltas: null,
  }))
  return { ...base, value: { ...base.value, methods, scores, variants } }
}

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      log: vi.fn(async () => log),
      layout: vi.fn(async () => layoutAnswer(doc)),
      releaseCards: vi.fn(async () => layoutAnswer(doc)),
      system: vi.fn(async () => system),
      calculations: vi.fn(async () => ({ value: [recorded] }) as Value<Call[]>),
      impact: vi.fn(async (_id: string, body: ImpactArguments) => answer(body)),
      contributions: vi.fn(async () => split),
    },
  }
})

function Place() {
  const location = useLocation()
  return <output data-testid="place">{`${location.pathname}${location.search}`}</output>
}

const nodes = (view: { container: HTMLElement }) => view.container.querySelectorAll('.react-flow__node').length
const place = () => screen.getByTestId('place').textContent ?? ''
const search = () => new URLSearchParams(place().split('?')[1] ?? '')
const impactBodies = () => vi.mocked(api.impact).mock.calls.map(([, body]) => body)
const splitBodies = () => vi.mocked(api.contributions).mock.calls.map(([, body]) => body)

async function open(calls: Call[] = [recorded]) {
  vi.mocked(api.calculations).mockResolvedValue({ value: calls } as Value<Call[]>)
  const view = renderInSlots(
    `/systems/${doc.id}`,
    <>
      <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: null, state: null }} />
      <Place />
    </>,
  )
  await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
  return view
}

const band = () => within(screen.getByRole('group', { name: 'Result band' }))
const status = () => band().getByRole('status')
const label = (name: string, score: number, unit: string) => `${name} ${formatAmount(score)} ${unit}`

beforeEach(() => {
  useUi.setState({ canvasSystemId: doc.id, canvasVariant: null, chosenEntry: null, resultCategories: {} })
  vi.mocked(api.impact).mockClear()
  vi.mocked(api.contributions).mockClear()
})

it('without a calculation the band offers calculate', async () => {
  await open([])
  await waitFor(() => expect(screen.getByRole('group', { name: 'Result band' })).toBeInTheDocument())
  expect(band().getByRole('button', { name: 'Calculate an impact result' })).toBeInTheDocument()
  expect(band().queryByRole('group', { name: 'Case shown' })).not.toBeInTheDocument()
})

it('the band names the calculation and each case it scored', async () => {
  await open([{ ...recorded, arguments: { ...recorded.arguments, variants: ['heavy'] } }])
  const shown = await screen.findByRole('group', { name: 'Case shown' })
  expect(band().getByTitle('gwp > climate change > GWP100')).toBeInTheDocument()
  const baseCase = within(shown).getByRole('button', { name: label('Base values', 4.158, 'kg CO2-Eq') })
  const heavy = within(shown).getByRole('button', { name: label('heavy', 5.548, 'kg CO2-Eq') })
  expect(baseCase).toHaveAttribute('aria-pressed', 'true')
  expect(heavy).toHaveAttribute('aria-pressed', 'false')
})

it('a case chosen in the band is the canvas state', async () => {
  await open([{ ...recorded, arguments: { ...recorded.arguments, variants: ['heavy'] } }])
  const shown = await screen.findByRole('group', { name: 'Case shown' })
  fireEvent.click(within(shown).getByRole('button', { name: /^heavy/ }))
  expect(useUi.getState().canvasVariant).toBe('heavy')
  await waitFor(() => expect(within(shown).getByRole('button', { name: /^heavy/ })).toHaveAttribute('aria-pressed', 'true'))
  expect(screen.getByLabelText('State')).toHaveValue('heavy')
  fireEvent.change(screen.getByLabelText('State'), { target: { value: 'lighter' } })
  await waitFor(() => expect(status()).toHaveTextContent('scenario lighter: not in this calculation'))
  expect(within(shown).getByRole('button', { name: /^Base values/ })).toHaveAttribute('aria-pressed', 'false')
  expect(within(shown).getByRole('button', { name: /^heavy/ })).toHaveAttribute('aria-pressed', 'false')
})

it('a state the calculation did not score offers to calculate with it', async () => {
  await open([{ ...recorded, arguments: { ...recorded.arguments, variants: ['heavy'] } }])
  fireEvent.change(await screen.findByLabelText('State'), { target: { value: 'lighter' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Calculate with it' }))
  expect(place().startsWith(`/systems/${doc.id}/results/impact?`)).toBe(true)
  expect(search().getAll('variants')).toEqual(['heavy', 'lighter'])
})

it('a case the system no longer holds is shown and not scored', async () => {
  await open([{ ...recorded, arguments: { ...recorded.arguments, variants: ['heavy', 'gone'] } }])
  const shown = await screen.findByRole('group', { name: 'Case shown' })
  const gone = within(shown).getByRole('button', { name: /^gone/ })
  expect(gone).toBeDisabled()
  expect(gone).toHaveTextContent('not in the system')
  await waitFor(() => expect(impactBodies().length).toBeGreaterThan(0))
  expect(impactBodies().some((body) => (body.variants ?? []).includes('gone'))).toBe(false)
  expect(impactBodies()).toContainEqual(expect.objectContaining({ variants: ['heavy'] }))
})

it('a calculation on another hash names both', async () => {
  await open()
  const line = `Recorded on ${shortHash(recorded.at_hash)}; computed here on the current model, ${shortHash(doc.hash)}.`
  await waitFor(() => expect(status()).toHaveTextContent(line))
})

it('a family shows one category chosen in the band', async () => {
  await open([{ ...recorded, arguments: { product_system_id: doc.id, impact_method: 'IPCC 2021' } }])
  const select = await screen.findByLabelText('Category')
  expect(within(select).getAllByRole('option')).toHaveLength(2)
  fireEvent.change(select, { target: { value: water.id } })
  await waitFor(() => expect(within(screen.getByRole('group', { name: 'Case shown' })).getByRole('button', { name: label('Base values', 0.42, 'm3 eq') })).toBeInTheDocument())
  await waitFor(() => expect(splitBodies()).toContainEqual(expect.objectContaining({ by: 'stage', method_id: water.id })))
  expect(splitBodies().some((body) => 'impact_method' in body)).toBe(false)
})

it("open result opens the result of the band's calculation", async () => {
  await open([{ ...recorded, arguments: { ...recorded.arguments, variants: ['heavy'] } }])
  fireEvent.click(band().getByRole('button', { name: 'Open result' }))
  expect(place()).toBe(`/systems/${doc.id}/results/impact?call=${recorded.id}`)
  fireEvent.click(within(screen.getByRole('group', { name: 'Case shown' })).getByRole('button', { name: /^heavy/ }))
  fireEvent.click(band().getByRole('button', { name: 'Open result' }))
  expect(search().get('variant')).toBe('heavy')
  expect(search().get('call')).toBe(recorded.id)
})
