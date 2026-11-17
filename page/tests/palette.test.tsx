import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App, Screens } from '@/App'
import { api } from '@/api/client'
import type { SystemRead } from '@/api/types'
import { useUi } from '@/store/ui'
import { shortHash } from '@/lib/format'
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
    useUi.setState({ pinned: [], details: null, lastDetails: null, canvasSystemId: null, inspector: 'open', sheetOpen: false, navOpen: false, paletteOpen: false })
  })

  afterEach(() => {
    vi.mocked(api.systems).mockImplementation(async () => systems)
    vi.mocked(api.system).mockImplementation(async () => system as unknown as SystemRead)
  })

  it('lists every menu item that can run by the path to it, and none that is disabled', () => {
    const all = menus({ systemId: null, resultOpen: false, openRequests: 0, theme: 'dark', inspector: 'open', inspectorShown: true, openInspector: nothing, closeInspector: nothing, toggleWidened: nothing, openNavigation: nothing, importFile: nothing, downloadResult: nothing, setTheme: nothing, newRequest: nothing, reorganise: nothing, resetLayout: nothing })
    const labels = leaves(all).map((item) => item.label)
    expect(labels).toContain('View › Theme › Light')
    expect(labels).toContain('View › Theme › ✓ Dark')
    expect(labels).toContain('View › Navigation')
    expect(labels).not.toContain('View › Activity')
    expect(labels.some((label) => label.startsWith('File › Export'))).toBe(false)
  })

  it('opens on Ctrl+K and runs the command that is chosen', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const box = await screen.findByPlaceholderText('Go to a process, a page or a command…')
    fireEvent.change(box, { target: { value: 'inspector' } })
    fireEvent.click(await screen.findByRole('option', { name: 'View › Inspector › Close' }))
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
    const option = await screen.findByRole('option', { name: new RegExp(process.name) })
    expect(within(option).getByText(process.code)).toBeInTheDocument()
    fireEvent.click(option)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
  })

  it('lists two systems of one name with their short ids and goes to the id chosen', async () => {
    const name = 'Cátodo de cobre — Chile (ruta pirometalúrgica)'
    const one = { ...systems.value[0], id: 'cc344688-1f2a-4c3d-9e4f-5a6b7c8d9e0f', name }
    const two = { ...systems.value[1], id: '4b0d7d27-2a3b-4c5d-8e9f-0a1b2c3d4e5f', name }
    vi.mocked(api.systems).mockResolvedValue({ ...systems, value: [one, two] } as unknown as typeof systems)
    renderAt(base, <Screens />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    await screen.findByPlaceholderText('Go to a process, a page or a command…')
    const items = await screen.findAllByRole('option', { name: /Cátodo de cobre/ })
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent(shortHash(one.id))
    expect(items[1]).toHaveTextContent(shortHash(two.id))
    const values = items.map((item) => item.getAttribute('data-value'))
    expect(values[0]).toContain(one.id)
    expect(values[1]).toContain(two.id)
    expect(new Set(values).size).toBe(2)
    fireEvent.click(items[0])
    await waitFor(() => expect(useUi.getState().canvasSystemId).toBe(one.id))
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const again = await screen.findAllByRole('option', { name: /Cátodo de cobre/ })
    fireEvent.click(again[1])
    await waitFor(() => expect(useUi.getState().canvasSystemId).toBe(two.id))
  })

  it('matches the words an item shows and the code of a process, not stray letters', async () => {
    const processes = [
      { ...system.value.processes[0], name: 'Refinería electrolítica', code: 'refinery' },
      { ...system.value.processes[1], name: 'Fundición', code: 'smelter' },
    ]
    vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, processes } } as unknown as SystemRead)
    renderAt(base, <Screens />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const box = await screen.findByPlaceholderText('Go to a process, a page or a command…')
    fireEvent.change(box, { target: { value: 'refi' } })
    expect(await screen.findByRole('option', { name: /Refinería electrolítica/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Fundición/ })).toBeNull()
    fireEvent.change(box, { target: { value: 'fundicion' } })
    expect(await screen.findByRole('option', { name: /Fundición/ })).toBeInTheDocument()
    fireEvent.change(box, { target: { value: 'smelter' } })
    expect(await screen.findByRole('option', { name: /Fundición/ })).toHaveTextContent('smelter')
  })
})
