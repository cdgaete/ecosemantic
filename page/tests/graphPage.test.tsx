import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import { api } from '@/api/client'
import type { ProductSystem } from '@/api/types'
import { colourOf } from '@/activity/agents'
import { GraphPage } from '@/editors/system/GraphPage'
import { useUi } from '@/store/ui'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import agentSystem from './fixtures/agent_system.json'
import agentLog from './fixtures/agent_log.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      log: vi.fn(async () => log),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      layout: vi.fn(async () => layoutAnswer(system.value as ProductSystem, agentSystem.value as ProductSystem)),
      releaseCards: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      validation: vi.fn(async () => {
        throw new original.ApiError(400, { error: 'invalid', message: "no process 'ghost' in 'widget'", details: {} })
      }),
    },
  }
})

const doc = system.value as ProductSystem

describe('graph page', () => {
  it('draws the graph of a system validation cannot answer for', async () => {
    const view = renderAt('/', <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: null }} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    expect(screen.queryByText(/validate a base process/)).not.toBeInTheDocument()
  })

  it('floats Calculate, the state, Fit and More on one toolbar at the bottom of the canvas', async () => {
    const view = renderAt('/', <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: null }} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    const bar = within(screen.getByRole('toolbar', { name: 'Canvas' }))
    expect(bar.getByRole('button', { name: 'Calculate an impact result' })).toBeInTheDocument()
    expect(bar.getByLabelText('State')).toBeInTheDocument()
    fireEvent.click(bar.getByRole('button', { name: 'Fit the graph' }))
    fireEvent.keyDown(bar.getByRole('button', { name: 'More canvas options' }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: /Focus the reference process/ }))
  })

  it('offers reorganising the graph and resetting what was placed under More, and releases on reset', async () => {
    const view = renderAt('/', <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: null }} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    const more = screen.getByRole('button', { name: 'More canvas options' })
    fireEvent.keyDown(more, { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: /Reorganise the graph/ }))
    fireEvent.keyDown(more, { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset layout' }))
    await waitFor(() => expect(api.releaseCards).toHaveBeenCalledWith(doc.id))
  })

  it('follows the build again once the layout is reset, so the reset arrangement is fitted', async () => {
    const view = renderAt('/', <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: null }} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    const more = screen.getByRole('button', { name: 'More canvas options' })
    fireEvent.keyDown(more, { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: /Focus the reference process/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: /Follow the build/ })).toBeInTheDocument())
    fireEvent.keyDown(more, { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset layout' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Follow the build/ })).not.toBeInTheDocument())
  })

  it('offers no calculation on the toolbar of a version that is not the latest', async () => {
    const view = renderAt('/', <GraphPage view={{ id: doc.id, system: doc, openRequests: 0, version: 'abc' }} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    const bar = within(screen.getByRole('toolbar', { name: 'Canvas' }))
    expect(bar.queryByRole('button', { name: 'Calculate an impact result' })).not.toBeInTheDocument()
    expect(bar.getByRole('button', { name: 'Fit the graph' })).toBeInTheDocument()
  })

  it("outlines the cards of the latest entry in its agent's colour", async () => {
    useUi.setState({ chosenEntry: null })
    vi.mocked(api.log).mockResolvedValue(agentLog as Awaited<ReturnType<typeof api.log>>)
    const built = agentSystem.value as ProductSystem
    const view = renderAt('/', <GraphPage view={{ id: built.id, system: built, openRequests: 0, version: null }} />)
    await waitFor(() => expect(view.container.querySelector<HTMLElement>('.react-flow__node > div')?.style.getPropertyValue('--outline')).toBe(colourOf('fixture-agent')))
  })
})
