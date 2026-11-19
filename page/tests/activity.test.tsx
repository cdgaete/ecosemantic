import { fireEvent, screen, within } from '@testing-library/react'
import { renderAt } from './render'
import { api } from '@/api/client'
import type { Call, Change, LogEntry, ProductSystem } from '@/api/types'
import { Trail } from '@/activity/Trail'
import { LogPage } from '@/editors/system/LogPage'
import { useUi } from '@/store/ui'
import agents from './fixtures/agents.json'
import agentLog from './fixtures/agent_log.json'
import agentSystem from './fixtures/agent_system.json'
import activityCalls from './fixtures/calls.json'
import openTrail from './fixtures/open_trail.json'
import rerun from './fixtures/rerun.json'
import trail from './fixtures/trail.json'
import trailCompute from './fixtures/trail_compute.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      log: vi.fn(async () => agentLog),
      agents: vi.fn(async () => agents),
      trail: vi.fn(async (_id: string, seq: number) => (seq === 3 ? trail : trailCompute)),
      openTrail: vi.fn(async () => openTrail),
      rerun: vi.fn(async () => rerun),
      activity: vi.fn(async () => activityCalls),
    },
  }
})

const doc = agentSystem.value as ProductSystem
const view = { id: doc.id, system: doc, openRequests: 0, version: null, state: null }
const EXCHANGE_ID = '83a0b3c9-fe45-458d-af5f-0f274210f630'

async function opened(seq: number): Promise<HTMLElement> {
  const button = (await screen.findByText(`#${seq}`)).closest('button') as HTMLElement
  fireEvent.click(button)
  return button.closest('li') as HTMLElement
}

describe('activity', () => {
  beforeEach(() => {
    useUi.setState({ chosenEntry: null, chosenProcess: null, seen: {}, since: {} })
  })

  it('shows the trail that led to an entry, with the chosen candidate marked and open to Details', async () => {
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(3)
    fireEvent.click(await within(entry).findByRole('button', { name: 'search_processes · get_background_process' }))
    expect(within(entry).getByText('get_background_process')).toBeInTheDocument()
    const candidate = within(entry).getAllByRole('link', { name: 'steel production' })[0]
    expect(candidate.getAttribute('href')).toContain('/databases/fixture/processes/')
    expect(within(entry).getAllByLabelText('chosen').length).toBeGreaterThan(0)
  })

  it('a trailing exchange id is drawn short', async () => {
    renderAt('/', <LogPage view={view} />)
    const short = await screen.findByTitle(EXCHANGE_ID)
    expect(short.textContent).toBe(EXCHANGE_ID.slice(0, 8))
    expect(short).toHaveClass('whitespace-nowrap', 'text-muted-foreground')
    expect(screen.getByText(/^updated exchange steel \(bottle\)/)).toBeInTheDocument()
    const plain = await screen.findByText('created product system bottle')
    expect(plain.hasAttribute('title')).toBe(false)
  })

  it("shows an agent's work in progress, with a failed call in the destructive colour", async () => {
    renderAt('/', <LogPage view={view} />)
    const progress = await screen.findByLabelText('Work in progress')
    const line = await within(progress).findByRole('button', { name: 'search_processes · get_background_process, 1 failed' })
    expect(line).toHaveClass('text-destructive')
    fireEvent.click(line)
    const failed = openTrail.value.find((call) => call.error !== null)!
    const message = await within(progress).findByText(failed.error!.message)
    expect(message).toHaveClass('text-destructive')
    expect(vi.mocked(api.openTrail).mock.calls.every(([, system]) => system === view.id)).toBe(true)
  })

  it('runs a calculation again and says the system changed since', async () => {
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(4)
    fireEvent.click(await within(entry).findByRole('button', { name: 'search_methods · calculate_impact' }))
    const item = (await within(entry).findByText('calculate_impact')).closest('li') as HTMLElement
    fireEvent.click(within(item).getByRole('button', { name: 'Run again' }))
    await within(item).findByText(/As of now/)
    const computed = trailCompute.value.find((call) => call.effect === 'compute')!
    expect(vi.mocked(api.rerun).mock.calls[0][0]).toBe(computed.id)
    const write = within(entry).getByText('update_exchange').closest('li') as HTMLElement
    expect(within(write).queryByRole('button', { name: 'Run again' })).not.toBeInTheDocument()
  })

  it('a trail lists its writes and opens its folded reads', () => {
    renderAt('/', <Trail calls={trail.value as unknown as Call[]} />)
    const run = screen.getByRole('button', { name: 'search_processes · get_background_process' })
    expect(run).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('steel production')).toBeNull()
    expect(screen.getByText('create_exchange')).toBeInTheDocument()
    expect(screen.getByText('amount: 0.5')).toBeInTheDocument()
    fireEvent.click(run)
    expect(run).toHaveAttribute('aria-expanded', 'true')
    const hits = screen.getAllByRole('link', { name: 'steel production' })
    expect(hits).toHaveLength(2)
    expect(hits[0].getAttribute('href')).toContain('/databases/fixture/processes/')
    expect(screen.getAllByLabelText('chosen')).toHaveLength(2)
  })

  it('a trail lists its writes and opens its folded reads with the log filtered to one process', async () => {
    useUi.setState({ chosenProcess: '9d9bff0b-a369-432f-bee5-e09865a1455d' })
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(5)
    const run = await within(entry).findByRole('button', { name: 'search_methods · calculate_impact' })
    expect(run).toHaveAttribute('aria-expanded', 'false')
    expect(within(entry).queryByText(/climate change/)).toBeNull()
    expect(within(entry).getByText('update_exchange')).toBeInTheDocument()
    fireEvent.click(run)
    expect(within(entry).getByText(/^fixture > gwp > climate change > GWP100: 1\.39 kg CO2-Eq$/)).toBeInTheDocument()
  })

  it('the failed calls are listed unfolded', async () => {
    const refused = activityCalls.value.at(-1)!
    const missed = { ...refused, id: 'missed', tool: 'search_processes', arguments: { database: 'fixture', query: 'missing' }, error: { error: 'not_found', message: "no method matches 'missing'", details: {} } }
    vi.mocked(api.activity).mockResolvedValue({ value: [missed, refused] } as unknown as Awaited<ReturnType<typeof api.activity>>)
    useUi.setState({ seen: { [view.id]: 3 }, since: { [view.id]: 3 } })
    renderAt('/', <LogPage view={view} />)
    fireEvent.click(await screen.findByRole('button', { name: '2 failed calls' }))
    expect(screen.getByText('query: missing')).toBeInTheDocument()
    expect(screen.getByText('process_id: missing')).toBeInTheDocument()
    expect(screen.getByText("no method matches 'missing'")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'search_processes · get_background_process, 2 failed' })).toBeNull()
  })

  it('shows every argument in words and adds the summary a call carries', () => {
    const base = trail.value[0] as unknown as Call
    const searched: Call = {
      ...base,
      id: 'searched',
      tool: 'search_processes',
      effect: 'read',
      arguments: { database: 'ecoinvent-3.12-cutoff', query: 'steel', limit: 2 },
      summary: { count: 0, more: false, noun: 'found', items: [], scores: [], demand: null },
    }
    const placed: Call = {
      ...base,
      id: 'placed',
      tool: 'arrange_graph',
      effect: 'write',
      arguments: { product_system_id: base.product_system_id, placements: [{ code: 'sen', x: 0, y: 236 }] },
      summary: {
        count: 2,
        more: false,
        noun: 'cards placed',
        items: [
          { label: 'sen', detail: null, kind: null, database: null, ref: null },
          { label: 'frame', detail: null, kind: null, database: null, ref: null },
        ],
        scores: [],
        demand: null,
      },
    }
    const laid: Call = {
      ...base,
      id: 'laid',
      tool: 'graph_layout',
      effect: 'read',
      arguments: {
        product_system_id: base.product_system_id,
        placements: Array.from({ length: 7 }, (_, n) => ({ code: `c${n}`, x: 0, y: n })),
      },
      summary: null,
    }
    renderAt('/', <Trail calls={[searched, placed, laid]} />)
    fireEvent.click(screen.getByRole('button', { name: 'search_processes' }))
    fireEvent.click(screen.getByRole('button', { name: 'graph_layout' }))
    const searching = screen.getByText('query: steel').closest('li') as HTMLElement
    expect(within(searching).getByText('limit: 2')).toBeInTheDocument()
    expect(within(searching).getByText('0 found')).toBeInTheDocument()
    const counted = screen.getByText('2 cards placed').closest('li') as HTMLElement
    expect(within(counted).getByText('placements: 1')).toBeInTheDocument()
    expect(within(counted).queryByText(/found/)).toBeNull()
    const quiet = screen.getByText('placements: 7').closest('li') as HTMLElement
    expect(quiet.textContent).not.toMatch(/[{}[\]]/)
  })

  it('a change names its entity’s kind and its name', async () => {
    const base = agentLog.value[2] as unknown as LogEntry
    const missing = '0b9d2f0e-1111-4111-8111-111111111111'
    const changes: Change[] = [
      { op: 'add', entity: 'process', id: 'bottle', field: null, before: null, after: null },
      { op: 'delete', entity: 'exchange', id: missing, field: null, before: null, after: null },
      { op: 'update', entity: 'parameter', id: 'frame_mass', field: 'value', before: 0.25, after: 0.5 },
    ]
    vi.mocked(api.log).mockResolvedValue({ ...agentLog, value: [{ ...base, seq: 9, message: 'built', changes }] } as unknown as Awaited<ReturnType<typeof api.log>>)
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(9)
    expect(within(entry).getByText('added process bottle')).toBeInTheDocument()
    expect(within(entry).getByText(`deleted exchange ${missing}`)).toBeInTheDocument()
    expect(within(entry).getByText('parameter frame_mass: value 0.25 → 0.5')).toBeInTheDocument()
  })
})
