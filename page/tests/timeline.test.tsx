import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { colourOfEntry } from '@/activity/agents'
import { Timeline } from '@/activity/Timeline'
import { api } from '@/api/client'
import type { Call, Effect, LogEntry } from '@/api/types'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import agentLog from './fixtures/agent_log.json'
import agents from './fixtures/agents.json'
import agentSystem from './fixtures/agent_system.json'
import openTrail from './fixtures/open_trail.json'

vi.mock('@/window/useWidth', () => ({ useWidth: () => 1048 }))

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      log: vi.fn(async () => agentLog),
      agents: vi.fn(async () => agents),
      openTrail: vi.fn(async () => openTrail),
    },
  }
})

const id = agentSystem.value.id
const entries = agentLog.value as unknown as LogEntry[]

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-11-13T18:38:00Z'))
  useUi.setState({ since: {}, seen: {}, chosenEntry: null, timelineOpen: true })
  useRequestDialog.setState({ target: null })
  vi.mocked(api.log).mockImplementation(async () => agentLog as Awaited<ReturnType<typeof api.log>>)
})

afterEach(() => {
  vi.useRealTimers()
})

const cards = (view: { container: HTMLElement }): HTMLElement[] => Array.from(view.container.querySelectorAll('ol > li'))

describe('the build timeline', () => {
  it('puts the trail in progress first and the newest entries after it', async () => {
    const view = renderAt('/', <Timeline systemId={id} />)
    await screen.findByText('fixture-agent · work in progress')
    await waitFor(() => expect(cards(view)).toHaveLength(4))
    const all = cards(view)
    expect(all[0]).toHaveTextContent('work in progress')
    expect(all[0]).toHaveTextContent('search_processes · get_background_process, 1 failed')
    expect(within(all[1]).getByText('#5')).toBeInTheDocument()
    expect(within(all[1]).getByTitle('agent fixture-agent')).toHaveTextContent('agent fixture-agent')
    expect(within(all[2]).getByText('#4')).toBeInTheDocument()
    expect(within(all[3]).getByText('#3')).toBeInTheDocument()
  })

  it('opens a request on the system', async () => {
    renderAt('/', <Timeline systemId={id} />)
    await screen.findByText('fixture-agent · work in progress')
    fireEvent.click(screen.getByRole('button', { name: 'New request' }))
    expect(useRequestDialog.getState().target).toEqual({ systemId: id })
  })

  it('chooses an entry as the log does', async () => {
    renderAt('/', <Timeline systemId={id} />)
    fireEvent.click(await screen.findByRole('button', { name: /#5/ }))
    expect(useUi.getState().chosenEntry).toEqual({ systemId: id, seq: 5, hash: entries[4].result_hash })
  })

  it("carries an entry card's agent colour", async () => {
    const view = renderAt('/', <Timeline systemId={id} />)
    await waitFor(() => expect(cards(view)).toHaveLength(4))
    const card = cards(view)[1]
    expect(within(card).getByText('#5')).toBeInTheDocument()
    expect(card).toHaveClass('border-l-2')
    expect(card.style.borderLeftColor).toBe(colourOfEntry(entries[4]))
    expect(cards(view)[0].style.borderLeftColor).toBe('')
  })

  it('a card folds its reads', async () => {
    renderAt('/', <Timeline systemId={id} />)
    const line = await screen.findByText('search_processes · get_background_process, 1 failed')
    expect(line).toHaveClass('truncate', 'text-destructive')
  })

  it('a card counts the calls of the parts it does not draw', async () => {
    const base = openTrail.value[0] as unknown as Call
    const made = (tool: string, effect: Effect, n: number): Call => ({ ...base, id: `${tool}-${n}`, tool, effect, outcome: 'ok' as const, summary: null, error: null })
    const long = [made('create_exchange', 'write', 1), made('search_processes', 'read', 2), made('get_background_process', 'read', 3), made('update_exchange', 'write', 4), made('search_methods', 'read', 5), made('calculate_impact', 'compute', 6), made('delete_exchange', 'write', 7)]
    vi.mocked(api.openTrail).mockImplementation(async () => ({ value: long }) as unknown as Awaited<ReturnType<typeof api.openTrail>>)
    const view = renderAt('/', <Timeline systemId={id} />)
    await screen.findByText('search_methods · calculate_impact')
    const card = cards(view)[0]
    expect(within(card).getByText('update_exchange · ok')).toBeInTheDocument()
    expect(within(card).getByText('delete_exchange · ok')).toBeInTheDocument()
    expect(within(card).queryByText('create_exchange · ok')).toBeNull()
    expect(within(card).getByText('+ 3 earlier calls in the full log')).toBeInTheDocument()
  })

  it('holds a long message whole in its title', async () => {
    const long = 'Steel sheet, hot rolled, coil, at the plant, produced with the electricity mix of the region as it stands today'
    vi.mocked(api.log).mockImplementation(
      async () => ({ ...agentLog, value: [...agentLog.value.slice(0, 4), { ...agentLog.value[4], message: long }] }) as Awaited<ReturnType<typeof api.log>>,
    )
    renderAt('/', <Timeline systemId={id} />)
    const whole = await screen.findByTitle(long)
    expect(whole).toHaveClass('line-clamp-2')
    expect(whole).toHaveTextContent(long)
  })

  it('folds to its header, keeps its buttons, and opens again', async () => {
    const view = renderAt('/', <Timeline systemId={id} />)
    await waitFor(() => expect(cards(view)).toHaveLength(4))
    const fold = screen.getByRole('button', { name: 'Build' })
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(fold)
    expect(cards(view)).toHaveLength(0)
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    expect(useUi.getState().timelineOpen).toBe(false)
    expect(screen.getByRole('button', { name: 'New request' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Full log/ })).toBeInTheDocument()
    fireEvent.click(fold)
    await waitFor(() => expect(cards(view)).toHaveLength(4))
  })

  it('opens folded when it was left folded', async () => {
    useUi.setState({ timelineOpen: false })
    const view = renderAt('/', <Timeline systemId={id} />)
    expect(await screen.findByRole('button', { name: 'Build' })).toHaveAttribute('aria-expanded', 'false')
    expect(cards(view)).toHaveLength(0)
  })
})
