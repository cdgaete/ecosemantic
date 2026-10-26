import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { App } from '@/App'
import { useUi } from '@/store/ui'
import { leaves } from '@/window/palette'
import { menus } from '@/window/menus'
import systems from './fixtures/systems.json'
import system from './fixtures/system.json'
import databases from './fixtures/databases.json'
import runs from './fixtures/runs.json'
import validation from './fixtures/validation.json'
import anchors from './fixtures/anchors.json'
import log from './fixtures/log.json'
import requests from './fixtures/requests.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import agents from './fixtures/agents.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      system: vi.fn(async () => system),
      databases: vi.fn(async () => databases),
      validation: vi.fn(async () => validation),
      anchors: vi.fn(async () => anchors),
      log: vi.fn(async () => log),
      requests: vi.fn(async () => requests),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      agents: vi.fn(async () => agents),
      runs: vi.fn(async () => runs),
    },
  }
})

const base = `/systems/${system.value.id}`
const nothing = (): void => undefined

describe('palette', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, trail: [], canvasSystemId: null, panelMode: 'beside', navOpen: false, navDocked: false, paletteOpen: false })
  })

  it('lists every menu item that can run by the path to it, and none that is disabled', () => {
    const all = menus({ systemId: null, resultOpen: false, openRequests: 0, theme: 'ecosemantic', panelMode: 'beside', openNavigation: nothing, importFile: nothing, downloadResult: nothing, setPanelMode: nothing, setTheme: nothing, newRequest: nothing, reorganise: nothing, resetLayout: nothing })
    const labels = leaves(all).map((item) => item.label)
    expect(labels).toContain('View › Theme › openLCA')
    expect(labels).toContain('View › Navigation')
    expect(labels).not.toContain('View › Activity')
    expect(labels.some((label) => label.startsWith('File › Export'))).toBe(false)
  })

  it('opens on Ctrl+K and runs the command that is chosen', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const box = await screen.findByPlaceholderText('Go to a process, a page or a command…')
    fireEvent.change(box, { target: { value: 'collapse' } })
    fireEvent.click(await screen.findByRole('option', { name: 'View › Panel › Collapse' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Activity' })).not.toBeInTheDocument())
    expect(screen.queryByPlaceholderText('Go to a process, a page or a command…')).not.toBeInTheDocument()
  })

  it('opens from a button on the top bar that names its keys', async () => {
    renderAt(base, <App router={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'Go to anything' }))
    expect(await screen.findByPlaceholderText('Go to a process, a page or a command…')).toBeInTheDocument()
  })

  it('goes to a process of the system on the canvas', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const process = system.value.processes[0]
    fireEvent.change(await screen.findByPlaceholderText('Go to a process, a page or a command…'), { target: { value: process.name } })
    fireEvent.click(await screen.findByRole('option', { name: new RegExp(process.name) }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
  })
})
