import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import { api } from '@/api/client'
import type { Answer, ImpactResult } from '@/api/types'
import { formatShare } from '@/lib/format'
import byPath from './fixtures/contributions_path.json'
import byProcess from './fixtures/contributions_process.json'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'
import { firstMethodOf } from './method'
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
      contributions: vi.fn(async (_id: string, body: { by: string }) => (body.by === 'path' ? byPath : byProcess)),
    },
  }
})

const search = `?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}`
// the fixture's one method is ('climate change', 'GWP100')
const label = 'climate change · GWP100'

it.each([
  ['processes', 'processes-category'],
  ['tree', 'tree-category'],
  ['sankey', 'sankey-category'],
])('names the indicator in the %s page category selector', async (page, selectId) => {
  renderAt(`/systems/${system.value.id}/results/${page}${search}`, <App router={false} />)
  await waitFor(() => expect(document.getElementById(selectId)?.querySelectorAll('option').length).toBeGreaterThan(0))
  expect(Array.from(document.getElementById(selectId)!.querySelectorAll('option')).map((o) => o.textContent)).toEqual([label])
})

it('names the indicator under the top contributions chart', async () => {
  renderAt(`/systems/${system.value.id}/results/general${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument())
})

const secondFamily = {
  id: 'm_second',
  impact_category: 'water use',
  impact_method: 'aware',
  indicator: 'water use',
  spec: 'fixture > aware > water use > water use',
  tuple: ['fixture', 'aware', 'water use', 'water use'],
  unit: 'm3',
}

const twoFamilies = {
  ...impact,
  value: {
    ...impact.value,
    methods: [...impact.value.methods, secondFamily],
    scores: [...impact.value.scores, { method_id: 'm_second', unit: 'm3', value: 1.2 }],
  },
}

it('the family every row shares is named once', async () => {
  renderAt(`/systems/${system.value.id}/results/impact${search}`, <App router={false} />)
  expect(await screen.findByText('Impact analysis: gwp')).toBeInTheDocument()
  const table = await screen.findByRole('table')
  expect(within(table).queryByRole('columnheader', { name: 'Method' })).not.toBeInTheDocument()
  expect(within(table).queryByRole('columnheader', { name: 'Category' })).not.toBeInTheDocument()
  expect(within(table).queryByText(/gwp/)).not.toBeInTheDocument()
  expect(within(table).getByRole('columnheader', { name: 'Indicator' })).toBeInTheDocument()
})

it('rows of two families get a Method column', async () => {
  vi.mocked(api.impact).mockResolvedValue(twoFamilies as Answer<ImpactResult>)
  // the amount is not 1, so this page is asked for its own calculation
  renderAt(`/systems/${system.value.id}/results/impact${search}&amount=2`, <App router={false} />)
  const table = await screen.findByRole('table')
  await waitFor(() => expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Name', 'Method', 'Indicator', 'Impact assessment result', 'Unit']))
  const cells = within(table).getAllByRole('cell').map((c) => c.textContent)
  expect(cells).toContain('gwp')
  expect(cells).toContain('aware')
  expect(cells).toContain('GWP100')
  expect(within(table).getAllByText('Method:')).toHaveLength(2)
})

function aligned(table: HTMLElement): void {
  const columns = within(table).getAllByRole('columnheader').length
  const rows = within(table).getAllByRole('row').filter((row) => row.querySelector('th') === null && row.querySelector('td[colspan]') === null)
  expect(rows.length).toBeGreaterThan(1)
  for (const row of rows) expect(within(row).getAllByRole('cell')).toHaveLength(columns)
}

async function openedImpact(path: string): Promise<HTMLElement> {
  renderAt(path, <App router={false} />)
  const table = await screen.findByRole('table')
  fireEvent.click(within(table).getAllByRole('button', { name: 'Expand' })[0])
  await waitFor(() => expect(within(table).getByText(/electricity production/)).toBeInTheDocument())
  return table
}

it("an opened category's rows line up with the table's columns", async () => {
  const family = firstMethodOf(impact.value)
  const bare = { ...family, indicator: family.impact_category }
  vi.mocked(api.impact).mockResolvedValue({ ...impact, value: { ...impact.value, methods: [bare] } } as Answer<ImpactResult>)
  const one = await openedImpact(`/systems/${system.value.id}/results/impact${search}&amount=5`)
  expect(within(one).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Name', 'Impact assessment result', 'Unit'])
  aligned(one)
  expect(within(one).getByText(/electricity production/).closest('td')).toHaveTextContent(formatShare(byProcess.value.processes[0].fraction))
  cleanup()

  vi.mocked(api.impact).mockResolvedValue(twoFamilies as Answer<ImpactResult>)
  const two = await openedImpact(`/systems/${system.value.id}/results/impact${search}&amount=2`)
  expect(within(two).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Name', 'Method', 'Indicator', 'Impact assessment result', 'Unit'])
  aligned(two)
})
