import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { App } from '@/App'
import { api } from '@/api/client'
import { useUi } from '@/store/ui'
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
    useUi.setState({ pinned: [], details: null, lastDetails: null, trail: [], canvasSystemId: null, panelMode: 'beside', navOpen: false, graphCovered: false, chosenEntry: null, chosenProcess: null, seen: {}, since: {} })
  })

  it('draw the system as it was at an older entry, read-only, and return to the latest', async () => {
    renderAt(`/systems/${id}`, <App router={false} />)
    fireEvent.click(await findEntry(2))
    await screen.findByText(/as it was at entry #2/)
    await waitFor(() => expect(api.version).toHaveBeenCalledWith(id, agentLog.value[1].result_hash))
    fireEvent.click(screen.getByRole('button', { name: 'Back to latest' }))
    expect(screen.queryByText(/as it was at entry #2/)).not.toBeInTheDocument()
    expect(useUi.getState().chosenEntry).toBeNull()
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
