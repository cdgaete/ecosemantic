import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import { App, Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, LogEntry, ProductSystem, SystemRead } from '@/api/types'
import { useUi } from '@/store/ui'
import { actorOf } from '@/activity/agents'
import { formatAgo } from '@/lib/format'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      system: vi.fn(async () => system),
      databases: vi.fn(async () => databases),
      version: vi.fn(async () => system.value),
      layout: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      releaseCards: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      log: vi.fn(async () => log),
      systemAs: vi.fn(async () => ({ ...(system as unknown as SystemRead), open_requests: 0 })),
      parameters: vi.fn(async () => ({ value: null })),
    },
  }
})

const hash = system.value.hash as string

const olderEntry = {
  ...log.value[0],
  seq: 1,
  message: 'created',
  result_hash: 'a'.repeat(64),
  timestamp: '2026-11-13T18:37:27.299687Z',
  actor: { id: null, kind: 'person', name: 'Carlos' },
} as unknown as LogEntry

const newestEntry = { ...log.value[0], seq: 2, message: 'updated the frame', result_hash: hash, timestamp: '2026-11-13T18:40:00.000000Z' } as unknown as LogEntry

const twoEntries = { ...log, value: [olderEntry, newestEntry] } as unknown as Answer<LogEntry[]>

const recordedLog = log as unknown as Answer<LogEntry[]>

describe('version editor', () => {
  afterEach(() => {
    vi.mocked(api.log).mockResolvedValue(recordedLog)
  })

  it('keeps every page tab inside the version and marks the open one active', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}/parameters`, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Pages' })).toBeInTheDocument())
    const nav = screen.getByRole('navigation', { name: 'Pages' })
    const links = within(nav).getAllByRole('link')
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) expect(link.getAttribute('href')).toContain(`/systems/${system.value.id}/versions/${hash}`)
    expect(within(nav).getByText('Parameters')).toHaveAttribute('aria-current', 'page')
  })

  it('names the log entry at that hash in the read-only banner', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}`, <App router={false} />)
    const banner = await screen.findByText(/^Read-only: the product system as it was at/)
    expect(banner).toHaveTextContent(`entry #${log.value[0].seq}`)
    expect(banner).toHaveTextContent(log.value[0].message)
  })

  it('says so when no log entry carries the hash on screen', async () => {
    renderAt(`/systems/${system.value.id}/versions/deadbeef`, <App router={false} />)
    await waitFor(() => expect(screen.getByText('No log entry names this hash.', { exact: false })).toBeInTheDocument())
  })

  it('says validation answers for the current document in place of the reference and validation rows', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    const line = screen.getByText('Validation answers for the current document, not for this version.')
    const link = within(line.parentElement!).getByRole('link', { name: 'Open the live product system' })
    expect(link.getAttribute('href')).toBe(`/systems/${system.value.id}`)
    expect(screen.queryByText('Reference')).toBeNull()
    expect(screen.queryByText('Target amount')).toBeNull()
  })

  it("leaves the validation rows and section off a version's Statistics page", async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}/statistics`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`Statistics – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.getByText('Validation answers for the current document, not for this version.')).toBeInTheDocument()
    expect(screen.queryByText('Connected graph / can calculate?')).toBeNull()
    expect(screen.queryByText('Reference process')).toBeNull()
    expect(screen.queryByText('Validation')).toBeNull()
    expect(screen.getByText('Number of processes')).toBeInTheDocument()
  })

  it("names the entry a version page was written at, with its own actor and a relative time", async () => {
    vi.mocked(api.log).mockResolvedValue(twoEntries)
    renderAt(`/systems/${system.value.id}/versions/${olderEntry.result_hash}`, <Screens />)
    await waitFor(() => expect(screen.getByText('Last change')).toBeInTheDocument())
    const line = screen.getByText('Last change').parentElement as HTMLElement
    expect(line).toHaveTextContent(actorOf(olderEntry))
    expect(line).not.toHaveTextContent(actorOf(newestEntry))
    const stamp = line.querySelector('time') as HTMLTimeElement
    expect(stamp.getAttribute('datetime')).toBe(olderEntry.timestamp)
    expect(stamp.getAttribute('title')).toBe(olderEntry.timestamp)
    expect(stamp.textContent).toBe(formatAgo(olderEntry.timestamp))
    expect(stamp.textContent).not.toContain('T')
  })

  it('leaves the canvas live when the live product system is opened from a version page', async () => {
    vi.mocked(api.log).mockResolvedValue(twoEntries)
    renderAt(`/systems/${system.value.id}`, <Screens />)
    fireEvent.click((await screen.findByText(`#${olderEntry.seq}`)).closest('button') as HTMLElement)
    await screen.findByText(`Read-only: the product system as it was at entry #${olderEntry.seq}.`)
    fireEvent.click(await screen.findByRole('link', { name: /^Open this version/ }))
    fireEvent.click(await screen.findByRole('link', { name: 'Open the live product system' }))
    await waitFor(() => expect(screen.queryByText(`Read-only: the product system as it was at entry #${olderEntry.seq}.`)).not.toBeInTheDocument())
    const bar = await screen.findByRole('toolbar', { name: 'Canvas' })
    expect(within(bar).getByRole('button', { name: 'Calculate an impact result' })).toBeInTheDocument()
  })

  it('an older entry is drawn as it was whatever state is chosen', async () => {
    useUi.setState({ canvasSystemId: system.value.id, canvasVariant: 'heavy', chosenEntry: null })
    const view = renderAt(`/systems/${system.value.id}/versions/${hash}`, <Screens />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    expect(vi.mocked(api.systemAs)).not.toHaveBeenCalled()
    expect(vi.mocked(api.layout).mock.calls.map((call) => call[1])).not.toContain('heavy')
    expect(vi.mocked(api.parameters).mock.calls.map((call) => call[2])).not.toContain('heavy')
    expect(screen.queryByText(/^Under (case|scenario) /)).toBeNull()
    expect(screen.getByLabelText('State')).toBeDisabled()
    useUi.setState({ canvasVariant: null })
  })
})
