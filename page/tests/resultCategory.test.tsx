import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { Screens } from '@/App'
import databases from './fixtures/databases.json'
import byPath from './fixtures/contributions_path.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

const first = impact.value.scores[0]
const second = { ...first, method: { ...first.method, id: 'm_second', impact_category: 'second category' } }
const twoCategories = { ...impact, value: { ...impact.value, scores: [first, second] } }

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
const search = `?impact_method=${encodeURIComponent(first.method.impact_method)}`
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
  await waitFor(() => expect(select.value).toBe(first.method.id))
  fireEvent.change(select, { target: { value: 'm_second' } })
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('category=m_second'))
  expect(screen.getByRole('link', { name: 'Sankey diagram' }).getAttribute('href')).toContain('category=m_second')
})
