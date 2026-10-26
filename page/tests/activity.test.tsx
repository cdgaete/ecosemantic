import { fireEvent, screen, within } from '@testing-library/react'
import { renderAt } from './render'
import { api } from '@/api/client'
import type { Call, ProductSystem } from '@/api/types'
import { Trail } from '@/activity/Trail'
import { LogPage } from '@/editors/system/LogPage'
import { useUi } from '@/store/ui'
import agents from './fixtures/agents.json'
import agentLog from './fixtures/agent_log.json'
import agentSystem from './fixtures/agent_system.json'
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
    },
  }
})

const doc = agentSystem.value as ProductSystem
const view = { id: doc.id, system: doc, openRequests: 0, version: null }

async function opened(seq: number): Promise<HTMLElement> {
  const button = (await screen.findByText(`#${seq}`)).closest('button') as HTMLElement
  fireEvent.click(button)
  return button.closest('li') as HTMLElement
}

describe('activity', () => {
  beforeEach(() => {
    useUi.setState({ chosenEntry: null, seen: {}, since: {} })
  })

  it('shows the trail that led to an entry, with the chosen candidate marked and open to Details', async () => {
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(3)
    await within(entry).findByText('search_processes')
    expect(within(entry).getByText('get_background_process')).toBeInTheDocument()
    const candidate = within(entry).getAllByRole('link', { name: 'steel production' })[0]
    expect(candidate.getAttribute('href')).toContain('/databases/fixture/processes/')
    expect(within(entry).getAllByLabelText('chosen').length).toBeGreaterThan(0)
  })

  it("shows an agent's work in progress, with a failed call in the destructive colour", async () => {
    renderAt('/', <LogPage view={view} />)
    const progress = await screen.findByLabelText('Work in progress')
    const failed = openTrail.value.find((call) => call.error !== null)!
    const message = await within(progress).findByText(failed.error!.message)
    expect(message).toHaveClass('text-destructive')
    expect(vi.mocked(api.openTrail).mock.calls.every(([, system]) => system === view.id)).toBe(true)
  })

  it('runs a calculation again and says the system changed since', async () => {
    renderAt('/', <LogPage view={view} />)
    const entry = await opened(4)
    const item = (await within(entry).findByText('calculate_impact')).closest('li') as HTMLElement
    fireEvent.click(within(item).getByRole('button', { name: 'Run again' }))
    await within(item).findByText(/As of now/)
    const computed = trailCompute.value.find((call) => call.effect === 'compute')!
    expect(vi.mocked(api.rerun).mock.calls[0][0]).toBe(computed.id)
    const write = within(entry).getByText('update_exchange').closest('li') as HTMLElement
    expect(within(write).queryByRole('button', { name: 'Run again' })).not.toBeInTheDocument()
  })

  it('folds a run of repeated calls into one row that unfolds', async () => {
    const base = trail.value[0] as unknown as Call
    const calls = [1, 2, 3].map((n) => ({ ...base, id: `a-${n}`, tool: 'arrange_graph', outcome: 'ok' as const, summary: null, error: null }))
    renderAt('/', <Trail calls={calls} />)
    const run = screen.getByRole('button', { name: /arrange_graph\s*×3/ })
    expect(run).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(run)
    expect(screen.getAllByText('arrange_graph')).toHaveLength(4)
  })

  it('folds the runs around a search and keeps the chosen mark on the search', () => {
    const base = trail.value[0] as unknown as Call
    const item = base.summary!.items[0]
    const quiet = (tool: string, n: number): Call => ({ ...base, id: `${tool}-${n}`, tool, outcome: 'ok' as const, summary: null, error: null })
    const searched: Call = { ...base, id: 'search-1', tool: 'search_processes' }
    const chose: Call = { ...base, id: 'chose-1', tool: 'update_exchange', effect: 'write', summary: null, arguments: { input: { database: item.database, id: item.ref } } }
    const calls = [quiet('arrange_graph', 1), quiet('arrange_graph', 2), quiet('arrange_graph', 3), searched, chose, quiet('graph_layout', 4), quiet('graph_layout', 5), quiet('graph_layout', 6)]
    renderAt('/', <Trail calls={calls} />)
    expect(screen.getByRole('button', { name: /arrange_graph\s*×3/ })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /graph_layout\s*×3/ })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('search_processes')).toBeInTheDocument()
    expect(screen.getAllByLabelText('chosen')).toHaveLength(1)
  })
})
