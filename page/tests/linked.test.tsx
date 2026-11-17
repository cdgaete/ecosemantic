import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import { App } from '@/App'
import { api } from '@/api/client'
import type { ProductSystem } from '@/api/types'
import { useLive } from '@/api/stream'
import { useUi } from '@/store/ui'
import { FakeSource } from './fakeSource'
import agents from './fixtures/agents.json'
import agentLog from './fixtures/agent_log.json'
import agentSystem from './fixtures/agent_system.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import openTrail from './fixtures/open_trail.json'
import requests from './fixtures/requests.json'
import runs from './fixtures/runs.json'
import systems from './fixtures/systems.json'
import trail from './fixtures/trail.json'
import validation from './fixtures/validation.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      system: vi.fn(async () => ({ ...agentSystem, open_requests: 0 })),
      version: vi.fn(async () => agentSystem.value),
      layout: vi.fn(async () => layoutAnswer(agentSystem.value as ProductSystem)),
      releaseCards: vi.fn(async () => layoutAnswer(agentSystem.value as ProductSystem)),
      databases: vi.fn(async () => databases),
      validation: vi.fn(async () => validation),
      anchors: vi.fn(async () => ({ value: ['bottle'], hint: null, view_url: null })),
      log: vi.fn(async () => agentLog),
      requests: vi.fn(async () => requests),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      runs: vi.fn(async () => runs),
      agents: vi.fn(async () => agents),
      openTrail: vi.fn(async () => openTrail),
      trail: vi.fn(async () => trail),
    },
  }
})

const id = agentSystem.value.id
const bottle = agentSystem.value.processes[0]
const entryButton = (seq: number) => screen.queryByText(`#${seq}`)?.closest('button') ?? null
const findEntry = async (seq: number) => (await screen.findByText(`#${seq}`)).closest('button') as HTMLElement

describe('the log and the graph', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, canvasSystemId: null, inspector: 'open', sheetOpen: false, navOpen: false, chosenEntry: null, chosenProcess: null, seen: {}, since: {} })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('draw the system as it was at an older entry, read-only, and return to the latest', async () => {
    renderAt(`/systems/${id}`, <App router={false} />)
    fireEvent.click(await findEntry(2))
    await screen.findByText(/as it was at entry #2/)
    await waitFor(() => expect(api.version).toHaveBeenCalledWith(id, agentLog.value[1].result_hash))
    fireEvent.click(screen.getByRole('button', { name: 'Back to latest' }))
    expect(screen.queryByText(/as it was at entry #2/)).not.toBeInTheDocument()
    expect(useUi.getState().chosenEntry).toBeNull()
  })

  it('keep the read-only canvas when a process page opens on a chosen entry', async () => {
    const view = renderAt(`/systems/${id}`, <App router={false} />)
    fireEvent.click(await findEntry(2))
    await screen.findByText(/as it was at entry #2/)
    const card = await waitFor(() => {
      const link = view.container.querySelector('.react-flow__node a') as HTMLAnchorElement | null
      expect(link).not.toBeNull()
      return link as HTMLAnchorElement
    })
    fireEvent.click(card)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
    expect(screen.getByText(/as it was at entry #2/)).toBeInTheDocument()
    expect(useUi.getState().chosenEntry?.seq).toBe(2)
  })

  it('follows the system while the canvas shows a chosen older entry', async () => {
    vi.stubGlobal('EventSource', FakeSource)
    FakeSource.instances = []
    renderAt(`/systems/${id}`, <App router={false} />)
    fireEvent.click(await findEntry(2))
    await screen.findByText(/as it was at entry #2/)
    fireEvent.click(screen.getByRole('button', { name: 'Close the inspector' }))
    await waitFor(() => expect(FakeSource.instances.length).toBeGreaterThan(0))
    const source = FakeSource.instances[0]
    const logged = vi.mocked(api.log).mock.calls.length
    const fresh = { ...agentLog.value[4], seq: 6 }
    act(() => source.emit('entry', { kind: 'entry', product_system_id: id, entry: fresh, request: null }))
    await waitFor(() => expect(useLive.getState().latest[id]?.seq).toBe(fresh.seq))
    await waitFor(() => expect(vi.mocked(api.log).mock.calls.length).toBeGreaterThan(logged))
  })

  it('choose the latest entry without leaving the live graph', async () => {
    renderAt(`/systems/${id}`, <App router={false} />)
    fireEvent.click(await findEntry(5))
    expect(useUi.getState().chosenEntry?.seq).toBe(5)
    expect(screen.queryByText(/as it was at entry/)).not.toBeInTheDocument()
  })

  it('filter the log to the process of a chosen card, and back', async () => {
    renderAt(`/systems/${id}`, <App router={false} />)
    await findEntry(1)
    act(() => useUi.getState().chooseProcess(bottle.id))
    expect(entryButton(1)).toBeNull()
    expect(entryButton(4)).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Clear process filter' }))
    expect(entryButton(1)).not.toBeNull()
  })
})
