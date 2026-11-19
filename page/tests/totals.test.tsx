import { screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, ImpactResult, Total, VariantScores } from '@/api/types'
import { formatAmount } from '@/lib/format'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { firstMethodOf } from './method'
import { renderAt } from './render'

const NOTICE = 'A weighted total rests on value choices, as this answer words it.'
const recorded = impact as unknown as Answer<ImpactResult>

function total(patch: Partial<Total> = {}): Total {
  return {
    impact_method: firstMethodOf(impact.value).impact_method,
    weighting_set: null,
    position: 0,
    unit: 'UBP',
    value: 1234.5,
    categories: [firstMethodOf(impact.value).id],
    normalised_by_zero: [],
    reason: null,
    value_choices: NOTICE,
    ...patch,
  }
}

function variant(name: string, delta: number, totals: Total[], totalDeltas: (number | null)[], value: number): VariantScores {
  return {
    name,
    scores: impact.value.scores.map((score) => ({ ...score, value })),
    deltas: impact.value.scores.map(() => delta),
    totals,
    total_deltas: totalDeltas,
    credit_loops: [],
    linked_credit_loops: [],
    treatments_run_backwards: [],
    uncertainty: null,
    paired_deltas: null,
  }
}

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
    },
  }
})

const address = `/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}`

function answering(totals: Total[], variants: VariantScores[] = []) {
  vi.mocked(api.impact).mockResolvedValue({ ...recorded, value: { ...recorded.value, totals, variants } })
  renderAt(address, <Screens />)
}

async function totalsTable(): Promise<HTMLElement> {
  const title = await screen.findByText('Totals')
  return within(title.closest('section')!).getByRole('table')
}

beforeEach(() => vi.clearAllMocks())

it("shows each weighting set's total under the categories, naming the set and the unit it answers in", async () => {
  const named = total({ weighting_set: 'Total (water resources, evaporated; for BAFU database)', position: 0, value: 1234.5, unit: 'UBP' })
  const unnamed = total({ weighting_set: null, position: 1, value: 0.5, unit: null })
  answering([named, unnamed])
  const table = await totalsTable()
  expect(within(table).getByText('Total (water resources, evaporated; for BAFU database)')).toBeInTheDocument()
  expect(within(table).getByText('Unnamed set 2')).toBeInTheDocument()
  expect(within(table).getByText(formatAmount(1234.5))).toBeInTheDocument()
  expect(within(table).getByText(formatAmount(0.5))).toBeInTheDocument()
  expect(within(table).getByText('UBP')).toBeInTheDocument()
  expect(within(table).getByText('no unit stated')).toBeInTheDocument()
})

it("states what each total rests on, in the answer's own words", async () => {
  answering([total({ weighting_set: 'evaporated', position: 0 })])
  await totalsTable()
  expect(screen.getByText(NOTICE)).toBeInTheDocument()
})

it('shows the reason a set gives no total in place of the value it gives none', async () => {
  const reason = 'its categories are in kg, m3 and MJ and it names no unit'
  answering([total({ weighting_set: 'environmental prices', position: 0, unit: null, value: null, reason })])
  const table = await totalsTable()
  expect(within(table).getByText(reason)).toBeInTheDocument()
  expect(within(table).getByText('environmental prices')).toBeInTheDocument()
  expect(within(table).getByText('no unit stated')).toBeInTheDocument()
})

it("shows each variant's total beside the base's and how far it moved", async () => {
  const base = total({ weighting_set: 'evaporated', position: 0, value: 1000, unit: 'UBP' })
  const delta = -260
  const small = total({ weighting_set: 'evaporated', position: 0, value: 750, unit: 'UBP' })
  // the answer states the move; 750 less 1000 would read −250
  answering([base], [variant('small', 750 - 1000, [small], [delta], 750)])
  const table = await totalsTable()
  const sign = delta >= 0 ? '+' : '−'
  const row = within(table).getByText('evaporated').closest('tr')!
  const cells = Array.from(row.querySelectorAll('td')).map((cell) => cell.textContent)
  expect(cells.slice(1)).toEqual([formatAmount(1000), 'UBP', `${formatAmount(750)} (${sign}${formatAmount(260)})`])
  expect(cells[0]).toContain('evaporated')
  expect(cells[0]).toContain(`${formatAmount(750)} (${sign}${formatAmount(260)})`)
})

it('draws no totals block where no weighting set gives a total', async () => {
  answering([])
  await waitFor(() => expect(screen.getByText('Sub-group by:')).toBeInTheDocument())
  expect(screen.queryByText('Totals')).not.toBeInTheDocument()
  expect(screen.queryByText(NOTICE)).not.toBeInTheDocument()
})
