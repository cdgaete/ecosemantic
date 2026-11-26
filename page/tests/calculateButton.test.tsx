import { fireEvent, screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { api } from '@/api/client'
import { CalculateButton } from '@/editors/system/CalculateButton'
import { useUi } from '@/store/ui'
import calculations from './fixtures/calculations.json'
import system from './fixtures/system.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      system: vi.fn(async () => system),
      calculations: vi.fn(async () => ({ value: [] })),
    },
  }
})

const id = system.value.id
const recorded = calculations.value[0]
type Recorded = Awaited<ReturnType<typeof api.calculations>>

function Place() {
  const location = useLocation()
  return <output data-testid="place">{`${location.pathname}${location.search}`}</output>
}

const button = (
  <>
    <CalculateButton systemId={id} />
    <Place />
  </>
)

beforeEach(() => {
  useUi.setState({ startedImpact: null })
  vi.mocked(api.calculations).mockResolvedValue({ value: [] } as unknown as Recorded)
})

it('opens the calculation form, and offers nothing to repeat while no calculation is recorded', async () => {
  renderAt(`/systems/${id}`, button)
  await waitFor(() => expect(api.calculations).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: /Run again/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'New calculation…' }))
  expect(screen.getByTestId('place').textContent).toBe(`/systems/${id}/results/setup`)
})

it('calculates the latest recorded calculation again in one click, as a calculation the person started', async () => {
  const family = { ...recorded, id: 'latest', arguments: { product_system_id: id, impact_method: 'IPCC 2021', variants: ['Solar bakery'] } }
  vi.mocked(api.calculations).mockResolvedValue({ value: [family, recorded] } as unknown as Recorded)
  renderAt(`/systems/${id}`, button)
  const again = await screen.findByRole('button', { name: 'Run again: IPCC 2021 · Solar bakery' })
  fireEvent.click(again)
  expect(screen.getByTestId('place').textContent).toBe(`/systems/${id}/results/impact?call=latest`)
  expect(useUi.getState().startedImpact).toBe(id)
})

it('names the base values when the latest calculation named no variant, and passes over one that failed', async () => {
  const failed = { ...recorded, id: 'failed', outcome: 'error', arguments: { product_system_id: id, impact_method: 'ReCiPe' } }
  const family = { ...recorded, id: 'good', arguments: { product_system_id: id, impact_method: 'IPCC 2021' } }
  vi.mocked(api.calculations).mockResolvedValue({ value: [failed, family] } as unknown as Recorded)
  renderAt(`/systems/${id}`, button)
  fireEvent.click(await screen.findByRole('button', { name: 'Run again: IPCC 2021 · base values' }))
  expect(screen.getByTestId('place').textContent).toBe(`/systems/${id}/results/impact?call=good`)
})
