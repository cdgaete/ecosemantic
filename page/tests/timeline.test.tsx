import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { colourOfEntry } from '@/activity/agents'
import { Timeline } from '@/activity/Timeline'
import { api } from '@/api/client'
import type { LogEntry } from '@/api/types'
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
  useUi.setState({ since: {}, seen: {}, chosenEntry: null })
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
    expect(all[0]).toHaveTextContent('search_processes · ok')
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
})
