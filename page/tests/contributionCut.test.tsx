import { fireEvent, screen, waitFor } from '@testing-library/react'
import { App } from '@/App'
import { api } from '@/api/client'
import type { Answer, ContributionResult } from '@/api/types'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import byProcess from './fixtures/contributions_process.json'
import system from './fixtures/system.json'
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
      system: vi.fn(async () => system),
      validation: vi.fn(async () => validation),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => byProcess),
    },
  }
})

const recorded = byProcess as Answer<ContributionResult>
const search = `?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
const answered = (cut: ContributionResult['cut']): Answer<ContributionResult> => ({ ...recorded, value: { ...recorded.value, cut } })
const last = () => vi.mocked(api.contributions).mock.calls.at(-1)![1]

beforeEach(() => vi.mocked(api.contributions).mockClear())

it('sends what the process page keeps as a share of the total, and says what it left out', async () => {
  vi.mocked(api.contributions).mockResolvedValue(answered({ cutoff: 0.01, below: 2, share: 0.004 }))
  renderAt(`/systems/${system.value.id}/results/processes${search}`, <App router={false} />)
  await waitFor(() => expect(api.contributions).toHaveBeenCalled())
  expect(last()).toMatchObject({ by: 'process', cutoff: 0.01 })
  expect(await screen.findByText('2 items under the 1.0 % cut-off are not shown, together 0.4 % of the total.')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } })
  await waitFor(() => expect(last()).toMatchObject({ cutoff: 0.05 }))
})

it('says nothing when the process page list kept every item', async () => {
  vi.mocked(api.contributions).mockResolvedValue(answered({ cutoff: 0.01, below: 0, share: 0 }))
  renderAt(`/systems/${system.value.id}/results/processes${search}&amount=2`, <App router={false} />)
  expect(await screen.findByText('Process contributions')).toBeInTheDocument()
  await waitFor(() => expect(api.contributions).toHaveBeenCalled())
  expect(screen.queryByText(/cut-off are not shown/)).toBeNull()
})

it('says what the general page left out of its top five', async () => {
  vi.mocked(api.contributions).mockResolvedValue(answered({ cutoff: 0.001, below: 3, share: 0.0027 }))
  renderAt(`/systems/${system.value.id}/results/general${search}`, <App router={false} />)
  expect(await screen.findByText('Top 5 direct contributions to impact category results - overview')).toBeInTheDocument()
  expect(await screen.findByText('3 items under the 0.1 % cut-off are not shown, together 0.3 % of the total.')).toBeInTheDocument()
})

it('sends what the impact page keeps as a share of the total, and says what it left out', async () => {
  vi.mocked(api.contributions).mockResolvedValue(answered({ cutoff: 0.01, below: 1, share: 0.002 }))
  renderAt(`/systems/${system.value.id}/results/impact${search}`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('Sub-group by:')).toBeInTheDocument())
  fireEvent.click(screen.getAllByRole('button', { name: 'Expand' })[0])
  await waitFor(() => expect(api.contributions).toHaveBeenCalled())
  expect(last()).toMatchObject({ cutoff: 0.01 })
  expect(await screen.findByText('1 item under the 1.0 % cut-off is not shown, together 0.2 % of the total.')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '2' } })
  await waitFor(() => expect(last()).toMatchObject({ cutoff: 0.02 }))
  fireEvent.click(screen.getAllByRole('radio')[1])
  await waitFor(() => expect(last()).toMatchObject({ by: 'flow', cutoff: 0.02 }))
})
