import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import type { ProductSystem } from '@/api/types'
import { LogPage } from '@/editors/system/LogPage'
import { useUi } from '@/store/ui'
import agents from './fixtures/agents.json'
import agentLog from './fixtures/agent_log.json'
import agentSystem from './fixtures/agent_system.json'
import calls from './fixtures/calls.json'
import openTrail from './fixtures/open_trail.json'
import trail from './fixtures/trail.json'
import validation from './fixtures/validation.json'

const refused = { ...calls.value[0], id: 'refused', entry_seq: null, outcome: 'error', summary: null, error: { error: 'invalid', message: 'an amount is a number', details: {} } }

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      log: vi.fn(async () => agentLog),
      agents: vi.fn(async () => agents),
      trail: vi.fn(async () => trail),
      openTrail: vi.fn(async () => openTrail),
      validation: vi.fn(async () => validation),
      activity: vi.fn(async () => ({ value: [refused] })),
    },
  }
})

const doc = agentSystem.value as ProductSystem
const view = { id: doc.id, system: doc, openRequests: 0, version: null }
const entryButton = (seq: number) => screen.queryByText(`#${seq}`)?.closest('button') ?? null
const entryOf = (seq: number) => screen.getByText(`#${seq}`).closest('li') as HTMLElement

describe('catch-up', () => {
  beforeEach(() => {
    useUi.setState({ chosenEntry: null, chosenProcess: null, seen: { [doc.id]: 3 }, since: {} })
  })

  it('heads Activity with what changed since the entry last seen, and marks the entries after it', async () => {
    renderAt('/', <LogPage view={view} />)
    const digest = await screen.findByLabelText('Since the entry last seen')
    expect(within(digest).getByText(/Since #3/)).toBeInTheDocument()
    expect(within(digest).getByRole('button', { name: '1 exchange added' })).toBeInTheDocument()
    expect(within(digest).getByRole('button', { name: '1 value edited' })).toBeInTheDocument()
    expect(within(digest).getByRole('button', { name: '0 processes added' })).toBeInTheDocument()
    expect(within(entryOf(4)).getByText('NEW')).toBeInTheDocument()
    expect(within(entryOf(5)).getByText('NEW')).toBeInTheDocument()
    expect(within(entryOf(3)).queryByText('NEW')).not.toBeInTheDocument()
    expect(useUi.getState().seen[doc.id]).toBe(5)
  })

  it('filters the log to what a count counted, and back', async () => {
    renderAt('/', <LogPage view={view} />)
    const count = await screen.findByRole('button', { name: '1 exchange added' })
    fireEvent.click(count)
    expect(count).toHaveAttribute('aria-pressed', 'true')
    expect(entryButton(5)).toBeNull()
    expect(entryButton(4)).not.toBeNull()
    fireEvent.click(count)
    expect(entryButton(5)).not.toBeNull()
  })

  it('lists the failed calls in place of the log', async () => {
    renderAt('/', <LogPage view={view} />)
    fireEvent.click(await screen.findByRole('button', { name: '1 failed call' }))
    expect(screen.getByText('an amount is a number')).toBeInTheDocument()
    expect(entryButton(3)).toBeNull()
  })

  it('has nothing new once everything is marked as seen', async () => {
    renderAt('/', <LogPage view={view} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark as seen' }))
    expect(screen.getByText('Nothing new since #5.')).toBeInTheDocument()
    expect(screen.queryByText('NEW')).not.toBeInTheDocument()
  })

  it('finds nothing new in a system never seen', async () => {
    useUi.setState({ seen: {}, since: {} })
    renderAt('/', <LogPage view={view} />)
    await waitFor(() => expect(screen.getByText('Nothing new since #5.')).toBeInTheDocument())
  })
})
