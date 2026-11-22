import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App, Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, Run } from '@/api/types'
import { formatAgo } from '@/lib/format'
import type { ProductSystem, SystemRead } from '@/api/types'
import { useUi } from '@/store/ui'
import system from './fixtures/system.json'
import validation from './fixtures/validation.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import log from './fixtures/log.json'
import requests from './fixtures/requests.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import runs from './fixtures/runs.json'

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
      elementaryFlow: vi.fn(async () => elementaryFlow),
      log: vi.fn(async () => log),
      requests: vi.fn(async () => requests),
      runs: vi.fn(async () => runs),
      systemAs: vi.fn(async (_id: string, variant: string) => {
        const base = system.value as ProductSystem
        const varied = variant !== 'heavy' ? base : { ...base, name: `${base.name} under the case` }
        return { ...(system as SystemRead), value: varied, open_requests: 0 }
      }),
    },
  }
})

const rootProcess = system.value.processes.find((p) => p.code === system.value.reference_process)!

describe('system editor', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows General information with the reference process the system names', async () => {
    renderAt(`/systems/${system.value.id}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.getByText('Reference')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText(rootProcess.name).length).toBeGreaterThan(0))
  })

  it('lists the log on its page', async () => {
    renderAt(`/systems/${system.value.id}/log`, <App router={false} />)
    const inspector = await screen.findByRole('complementary', { name: 'Inspector' })
    await waitFor(() => expect(within(inspector).getByText(log.value[0].message)).toBeInTheDocument())
  })

  it('lists the requests on its page', async () => {
    renderAt(`/systems/${system.value.id}/requests`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(requests.value[0].message)).toBeInTheDocument())
  })

  it('says when a request and its outcome were made as how long ago, keeping each instant on it', async () => {
    const answered = requests.value[1]
    const outcome = answered.outcome!
    // a millisecond before the request is nine hours old: a clock that moved between the page and the test would read 9
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(new Date(answered.timestamp).getTime() + 9 * 3_600_000 - 1))
    renderAt(`/systems/${system.value.id}/requests`, <App router={false} />)
    const row = (await screen.findByText(answered.message)).closest('li') as HTMLElement
    const stamps = [...row.querySelectorAll('time')]
    expect(stamps).toHaveLength(2)
    expect(stamps[0].getAttribute('datetime')).toBe(answered.timestamp)
    expect(stamps[0].getAttribute('title')).toBe(answered.timestamp)
    expect(stamps[0].textContent).toBe('8 h ago')
    expect(stamps[0].textContent).toBe(formatAgo(answered.timestamp))
    expect(stamps[1].getAttribute('datetime')).toBe(outcome.timestamp)
    expect(stamps[1].getAttribute('title')).toBe(outcome.timestamp)
    expect(stamps[1].textContent).toBe(formatAgo(outcome.timestamp))
  })

  it('lists the simulations, each opening its editor', async () => {
    renderAt(`/systems/${system.value.id}/simulations`, <App router={false} />)
    const first = runs.value[0]
    const link = await waitFor(() => within(screen.getByRole('table')).getByRole('link', { name: first.status }))
    const table = screen.getByRole('table')
    expect(link.getAttribute('href')).toContain(`/systems/${system.value.id}/simulations/${first.id}`)
    expect(within(table).getByText(first.methods[0].impact_method)).toBeInTheDocument()
    expect(within(table).queryByText(/an earlier state/)).not.toBeInTheDocument()
  })

  it('marks a simulation computed on an earlier state', async () => {
    vi.mocked(api.runs).mockResolvedValueOnce({ ...runs, value: [{ ...runs.value[0], at_hash: 'f'.repeat(64) }] } as unknown as Answer<Run[]>)
    // App's own client already holds the runs read above; Screens reads through a fresh one
    renderAt(`/systems/${system.value.id}/simulations`, <Screens />)
    await waitFor(() => expect(screen.getByText(/an earlier state/)).toBeInTheDocument())
  })

  it('names each request by what it asks of the agent', async () => {
    renderAt(`/systems/${system.value.id}/requests`, <App router={false} />)
    const returned = requests.value[0]
    const returnedRow = (await screen.findByText(returned.message)).closest('li') as HTMLElement
    expect(within(returnedRow).getByText('Return with an objection')).toBeInTheDocument()
    const changed = requests.value[1]
    const changedRow = (await screen.findByText(changed.message)).closest('li') as HTMLElement
    expect(within(changedRow).getByText('Ask for a change to')).toBeInTheDocument()
  })

  it('names the state the canvas shows on general information and on statistics', async () => {
    useUi.setState({ canvasSystemId: system.value.id, canvasVariant: 'heavy' })
    const general = renderAt(`/systems/${system.value.id}/general`, <App router={false} />)
    expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
    expect(vi.mocked(api.systemAs)).toHaveBeenCalledWith(system.value.id, 'heavy')
    general.unmount()
    renderAt(`/systems/${system.value.id}/statistics`, <App router={false} />)
    expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
    useUi.setState({ canvasVariant: null })
  })

  it('names no state on the log page', async () => {
    useUi.setState({ canvasSystemId: system.value.id, canvasVariant: 'heavy' })
    renderAt(`/systems/${system.value.id}/log`, <App router={false} />)
    await waitFor(() => expect(screen.getByText('Entries')).toBeInTheDocument())
    expect(screen.queryByText(/^Under (case|scenario) /)).toBeNull()
    useUi.setState({ canvasVariant: null })
  })
})
