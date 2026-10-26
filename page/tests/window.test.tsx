import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import type { ProductSystem } from '@/api/types'
import { App } from '@/App'
import { rememberToken } from '@/api/client'
import { useUi } from '@/store/ui'
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
      runs: vi.fn(async () => ({ ...runs, value: [{ ...runs.value[0], status: 'running', open: true }] })),
      layout: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      calculations: vi.fn(async () => ({ value: [] })),
    },
  }
})

const base = `/systems/${system.value.id}`

describe('window', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, trail: [], canvasSystemId: null, panelMode: 'beside', navOpen: false, navDocked: false, graphCovered: false })
  })

  it('opens a system as its graph with Activity beside it', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    await waitFor(() => expect(screen.getByText(log.value[0].message)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page')
  })

  it('says when a log entry was made as how long ago, and keeps the instant on it', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByText(log.value[0].message)).toBeInTheDocument())
    const stamp = view.container.querySelector('time') as HTMLTimeElement
    expect(stamp.getAttribute('datetime')).toBe(log.value[0].timestamp)
    expect(stamp.getAttribute('title')).toBe(log.value[0].timestamp)
    expect(stamp.textContent).not.toContain('T')
  })

  it('keeps the graph while Details holds a page of the system, and names the way back', async () => {
    const view = renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0)
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(within(crumbs).getByRole('link', { name: system.value.name })).toHaveAttribute('href', expect.stringContaining(base))
  })

  it('leads back to the list of product systems from the top bar, the breadcrumb and the navigation', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    const home = /^\/(\?|$)/
    const crumbs = within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getAllByRole('link')
    expect(crumbs[0]).toHaveTextContent('Product systems')
    expect(crumbs[0].getAttribute('href')).toMatch(home)
    fireEvent.click(screen.getByRole('button', { name: 'Show navigation' }))
    const nav = await screen.findByRole('complementary')
    expect(within(nav).getByRole('link', { name: /Product systems/ }).getAttribute('href')).toMatch(home)
    fireEvent.click(screen.getByRole('link', { name: 'EcoSemantic' }))
    expect(await screen.findByRole('heading', { name: 'Product systems' })).toBeInTheDocument()
  })

  it('gives the panel the whole width when expanded, and back', async () => {
    const view = renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Expand panel' }))
    expect(view.container.querySelectorAll('.react-flow__node').length).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'Show graph' }))
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
  })

  it('collapses the panel to a rail that leaves the graph the width, and the rail opens it again', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Collapse panel' }))
    expect(screen.queryByRole('link', { name: 'Activity' })).not.toBeInTheDocument()
    expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0)
    const rail = screen.getByRole('toolbar', { name: 'Panel' })
    fireEvent.click(within(rail).getByRole('button', { name: 'Show Activity' }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page'))
  })

  it('opens Details from the rail of a collapsed panel', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Collapse panel' }))
    fireEvent.click(within(screen.getByRole('toolbar', { name: 'Panel' })).getByRole('button', { name: 'Show Details' }))
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
  })

  it('opens a collapsed panel when a card on the graph is followed', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Collapse panel' }))
    const card = view.container.querySelector('.react-flow__node a') as HTMLAnchorElement
    fireEvent.click(card)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
  })

  it('collapses the panel and shows it again on Ctrl+Alt+B', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    expect(screen.queryByRole('link', { name: 'Activity' })).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument()
  })

  it('leaves a shortcut typed into a field to the field', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    const field = document.createElement('input')
    document.body.append(field)
    fireEvent.keyDown(field, { key: 'b', ctrlKey: true, altKey: true })
    field.remove()
    expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument()
  })

  it('pins what Details holds as a tab that unpins', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Pin' }))
    const strip = screen.getByRole('tablist')
    expect(within(strip).getByRole('tab', { name: new RegExp(system.value.name) })).toBeInTheDocument()
    fireEvent.click(within(strip).getByRole('button', { name: `Unpin ${system.value.name}` }))
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('states the validation and the open requests as badges', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: /Valid|issue/ })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /request/ })).toHaveAttribute('href', expect.stringContaining(`${base}/requests`))
  })

  it('lists product systems and background databases in the navigation sheet', async () => {
    rememberToken('?token=t')
    renderAt('/?token=t', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary')
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    expect(within(nav).getByText('Background databases')).toBeInTheDocument()
    const link = within(nav).getByText(system.value.name).closest('a')
    expect(link?.getAttribute('href')).toContain(`${base}?token=t`)
  })

  it('docks the navigation beside the graph from the top bar, and takes it away again', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Show navigation' }))
    const nav = await screen.findByRole('complementary')
    await waitFor(() => expect(within(nav).getByText('Background databases')).toBeInTheDocument())
    expect(view.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hide navigation' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('keeps the docked navigation when a link in it is followed', async () => {
    renderAt('/', <App router={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show navigation' }))
    const nav = await screen.findByRole('complementary')
    fireEvent.click(await within(nav).findByText(system.value.name))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument())
    expect(screen.getByRole('complementary')).toBeInTheDocument()
  })

  it('closes the navigation sheet when a link in it is followed', async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary')
    fireEvent.click(await within(nav).findByText(system.value.name))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('docks and takes away the navigation on Ctrl+B', async () => {
    renderAt(base, <App router={false} />)
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true })
    expect(await screen.findByRole('complementary')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true })
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('keeps the window mounted on an address no editor answers yet', () => {
    rememberToken('?token=t')
    renderAt('/databases/fixture/nothing/none?token=t', <App router={false} />)
    expect(screen.getByText('This page has no editor for /databases/fixture/nothing/none.')).toBeInTheDocument()
  })

  it("marks a system's Simulations node while one of its runs is open", async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary')
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    fireEvent.click(within(nav).getAllByRole('button', { name: 'Expand' })[0])
    await waitFor(() => expect(within(nav).getByText('Simulations')).toBeInTheDocument())
    await waitFor(() => expect(within(nav).getByText('running')).toBeInTheDocument())
  })

  it('draws no strip of agents under the top bar', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.queryByLabelText('Agents')).toBeNull()
  })

  it("links a system's Results in the navigation to the results on record", async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary')
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    fireEvent.click(within(nav).getAllByRole('button', { name: 'Expand' })[0])
    const results = await within(nav).findByRole('link', { name: /^Results/ })
    expect(results.getAttribute('href')).toMatch(/^\/systems\/[^/]+\/results(\?|$)/)
  })
})
