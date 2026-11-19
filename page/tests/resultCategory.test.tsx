import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { Screens } from '@/App'
import { api } from '@/api/client'
import { useUi } from '@/store/ui'
import type { Answer, ImpactResult } from '@/api/types'
import databases from './fixtures/databases.json'
import byPath from './fixtures/contributions_path.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'
import { firstMethodOf } from './method'

const first = impact.value.scores[0]
const firstMethod = firstMethodOf(impact.value)
const secondMethod = { ...firstMethod, id: 'm_second', impact_category: 'second category' }
const second = { ...first, method_id: 'm_second' }
const twoCategories = { ...impact, value: { ...impact.value, methods: [firstMethod, secondMethod], scores: [first, second] } }

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
      vocabulary: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      impact: vi.fn(async () => twoCategories),
      contributions: vi.fn(async () => byPath),
      inventory: vi.fn(async () => inventory),
    },
  }
})

function Address() {
  const location = useLocation()
  return <output data-testid="address">{location.search}</output>
}

const base = `/systems/${system.value.id}/results`
const search = `?impact_method=${encodeURIComponent(firstMethod.impact_method)}`
const pages = [
  ['processes', 'Impact category'],
  ['tree', 'Impact category'],
  ['sankey', 'Impact category:'],
] as const

it('opens every result page on the category its address names', async () => {
  for (const [page, label] of pages) {
    renderAt(`${base}/${page}${search}&category=m_second`, <Screens />)
    const select = (await screen.findByLabelText(label)) as HTMLSelectElement
    await waitFor(() => expect(select.value).toBe('m_second'))
    cleanup()
  }
})

it('writes the chosen category into the address, which the other result pages carry', async () => {
  renderAt(`${base}/tree${search}`, <><Screens /><Address /></>)
  const select = (await screen.findByLabelText('Impact category')) as HTMLSelectElement
  await waitFor(() => expect(select.value).toBe(first.method_id))
  fireEvent.change(select, { target: { value: 'm_second' } })
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('category=m_second'))
  expect(screen.getByRole('link', { name: 'Sankey diagram' }).getAttribute('href')).toContain('category=m_second')
})

const systemId = system.value.id
const firstZero = { ...twoCategories, value: { ...twoCategories.value, scores: [{ ...first, value: 0 }, second] } }
const allZero = { ...twoCategories, value: { ...twoCategories.value, scores: [{ ...first, value: 0 }, { ...second, value: 0 }] } }

beforeEach(() => {
  useUi.setState({ resultCategories: {} })
})

const categorySelect = async () => (await screen.findByLabelText('Impact category')) as HTMLSelectElement

it('process results open on the category last chosen for the system', async () => {
  renderAt(`${base}/processes${search}`, <Screens />)
  const select = await categorySelect()
  await waitFor(() => expect(select.value).toBe(first.method_id))
  fireEvent.change(select, { target: { value: 'm_second' } })
  await waitFor(() => expect(select.value).toBe('m_second'))
  cleanup()
  renderAt(`${base}/processes${search}`, <Screens />)
  const again = await categorySelect()
  await waitFor(() => expect(again.value).toBe('m_second'))
})

it('a first visit opens on the first category whose score is not 0', async () => {
  vi.mocked(api.impact).mockResolvedValue(firstZero as Answer<ImpactResult>)
  renderAt(`${base}/processes${search}&amount=2`, <Screens />)
  const select = await categorySelect()
  await waitFor(() => expect(select.value).toBe('m_second'))
})

it('scores all 0 open on the first', async () => {
  vi.mocked(api.impact).mockResolvedValue(allZero as Answer<ImpactResult>)
  renderAt(`${base}/processes${search}&amount=3`, <Screens />)
  const select = await categorySelect()
  await waitFor(() => expect(select.value).toBe(first.method_id))
})

it('a category of another family is not kept', async () => {
  useUi.setState({ resultCategories: { [systemId]: 'm_gone' } })
  renderAt(`${base}/processes${search}`, <Screens />)
  const select = await categorySelect()
  await waitFor(() => expect(select.value).toBe(first.method_id))
})
