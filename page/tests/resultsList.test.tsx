import { fireEvent, screen, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { Call, Value } from '@/api/types'
import agentSystem from './fixtures/agent_system.json'
import calculations from './fixtures/calculations.json'
import databases from './fixtures/databases.json'
import families from './fixtures/vocabulary_impact_methods.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => agentSystem),
      validation: vi.fn(async () => validation),
      vocabulary: vi.fn(async () => families),
      calculations: vi.fn(async () => calculations),
    },
  }
})

const id = agentSystem.value.id
const recorded = calculations.value[0] as Call
const answer = (value: Call[]): Value<Call[]> => ({ value })

beforeEach(() => vi.mocked(api.calculations).mockResolvedValue(calculations as Value<Call[]>))

it('lists the calculations on record, each opening its result by its call', async () => {
  renderAt(`/systems/${id}/results`, <Screens />)
  expect(await screen.findByRole('heading', { name: `Results – ${agentSystem.value.name}` })).toBeInTheDocument()
  const open = await screen.findByRole('link', { name: 'Open' })
  expect(open.getAttribute('href')).toBe(`/systems/${id}/results/impact?call=${recorded.id}`)
  expect(screen.getAllByText(recorded.agent).length).toBeGreaterThan(0)
  expect(within(open.closest('li')!).getByText('base values')).toBeInTheDocument()
})

it('marks a calculation made on an earlier version', async () => {
  vi.mocked(api.calculations).mockResolvedValue(answer([{ ...recorded, at_hash: 'feedbeef00' }]))
  renderAt(`/systems/${id}/results`, <Screens />)
  expect(await screen.findByText(/an earlier version/)).toBeInTheDocument()
})

it('unfolds every score the record holds', async () => {
  const first = recorded.summary!.scores[0]
  const scores = [first, { ...first, method: `${first.method} two`, value: 2 }, { ...first, method: `${first.method} three`, value: 3 }]
  vi.mocked(api.calculations).mockResolvedValue(answer([{ ...recorded, summary: { ...recorded.summary!, scores } }]))
  renderAt(`/systems/${id}/results`, <Screens />)
  fireEvent.click(await screen.findByRole('button', { name: 'and 2 more' }))
  expect(screen.getByText(/two:/)).toBeInTheDocument()
  expect(screen.getByText(/three:/)).toBeInTheDocument()
})

it('shows a failed calculation with its error and nothing to open', async () => {
  vi.mocked(api.calculations).mockResolvedValue(answer([{ ...recorded, outcome: 'error', summary: null, error: { error: 'not_found', message: 'no method m_missing', details: {} } }]))
  renderAt(`/systems/${id}/results`, <Screens />)
  expect(await screen.findByText('no method m_missing')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Open' })).not.toBeInTheDocument()
})

it('says none is recorded and starts a new calculation', async () => {
  vi.mocked(api.calculations).mockResolvedValue(answer([]))
  renderAt(`/systems/${id}/results`, <Screens />)
  expect(await screen.findByText(/No calculation is recorded/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /New calculation/ }))
  expect(await screen.findByText(`Calculation – ${agentSystem.value.name}`)).toBeInTheDocument()
})
