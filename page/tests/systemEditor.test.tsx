import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App, Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, Run } from '@/api/types'
import system from './fixtures/system.json'
import validation from './fixtures/validation.json'
import anchors from './fixtures/anchors.json'
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
      anchors: vi.fn(async () => anchors),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      log: vi.fn(async () => log),
      requests: vi.fn(async () => requests),
      runs: vi.fn(async () => runs),
    },
  }
})

const rootProcess = system.value.processes.find((p) => p.code === system.value.reference_process)!

describe('system editor', () => {
  it('shows General information with the reference process the system names', async () => {
    renderAt(`/systems/${system.value.id}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.getByText('Reference')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText(rootProcess.name).length).toBeGreaterThan(0))
  })

  it('lists the log on its page', async () => {
    renderAt(`/systems/${system.value.id}/log`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(log.value[0].message)).toBeInTheDocument())
  })

  it('lists the requests on its page', async () => {
    renderAt(`/systems/${system.value.id}/requests`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(requests.value[0].message)).toBeInTheDocument())
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
})
