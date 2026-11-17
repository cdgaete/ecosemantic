import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { resizePage } from './setup'
import { layoutAnswer } from './placements'
import { firstMethodOf } from './method'
import type { Answer, LogEntry, ProductSystem } from '@/api/types'
import { useLive } from '@/api/stream'
import { App, Screens } from '@/App'
import { api, rememberToken } from '@/api/client'
import { shortHash } from '@/lib/format'
import { useUi } from '@/store/ui'
import { NavPane } from '@/window/NavPane'
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
import impact from './fixtures/impact.json'
import contributions from './fixtures/contributions_path.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      system: vi.fn(async () => system),
      version: vi.fn(async () => system.value),
      databases: vi.fn(async () => databases),
      validation: vi.fn(async () => validation),
      anchors: vi.fn(async () => anchors),
      log: vi.fn(async () => log),
      requests: vi.fn(async () => requests),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      agents: vi.fn(async () => agents),
      runs: vi.fn(async () => ({ ...runs, value: [{ ...runs.value[0], status: 'running', open: true }] })),
      layout: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      releaseCards: vi.fn(async () => layoutAnswer(system.value as ProductSystem)),
      calculations: vi.fn(async () => ({ value: [] })),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => contributions),
    },
  }
})

const base = `/systems/${system.value.id}`

const nodes = (view: { container: HTMLElement }) => view.container.querySelectorAll('.react-flow__node').length

// A page's own `<header>` is a banner to testing-library too; the frame's name island is the one the clearance measures.
const nameIsland = () => screen.getAllByRole('banner').find((element) => element.dataset.clear === 'top')!

const rowsOf = (element: Element): number[] => {
  const tokens = element.className.split(/\s+/)
  const start = Number(tokens.find((token) => /^row-start-\d+$/.test(token))?.split('-').at(-1) ?? 1)
  const span = Number(tokens.find((token) => /^row-span-\d+$/.test(token))?.split('-').at(-1) ?? 1)
  return Array.from({ length: span }, (_, index) => start + index)
}

describe('window', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, canvasSystemId: null, inspector: 'open', sheetOpen: false, navOpen: false })
  })

  afterEach(() => {
    window.innerWidth = 1024
  })

  it('opens a system as its graph with Activity beside it', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    await waitFor(() => expect(within(screen.getByRole('complementary', { name: 'Inspector' })).getByText(log.value[0].message)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page')
  })

  it('says when a log entry was made as how long ago, and keeps the instant on it', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    const inspector = screen.getByRole('complementary', { name: 'Inspector' })
    await waitFor(() => expect(within(inspector).getByText(log.value[0].message)).toBeInTheDocument())
    const stamp = inspector.querySelector('time') as HTMLTimeElement
    expect(stamp.getAttribute('datetime')).toBe(log.value[0].timestamp)
    expect(stamp.getAttribute('title')).toBe(log.value[0].timestamp)
    expect(stamp.textContent).not.toContain('T')
  })

  it('draws the graph under the dock, the name island and the inspector', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    expect(screen.getByRole('toolbar', { name: 'Frame' })).toBeInTheDocument()
    const banner = screen.getByRole('banner')
    expect(within(banner).getByRole('heading', { name: system.value.name })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Inspector' })).toBeInTheDocument()
  })

  it('draws the list of product systems in place of the graph', async () => {
    const view = renderAt('/', <App router={false} />)
    await screen.findByRole('region', { name: 'Page' })
    const banner = nameIsland()
    expect(within(banner).getByRole('heading', { name: 'Product systems' })).toBeInTheDocument()
    expect(within(banner).queryByText('Live')).not.toBeInTheDocument()
    const page = screen.getByRole('region', { name: 'Page' })
    for (const card of systems.value) expect(await within(page).findByText(card.name)).toBeInTheDocument()
    expect(within(page).getByRole('table')).toBeInTheDocument()
    expect(view.container.querySelector('.react-flow')).toBeNull()
    expect(screen.queryByRole('complementary', { name: 'Inspector' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zoom in' })).not.toBeInTheDocument()
  })

  it('leads from the explorer back to the graph of the system on the canvas', async () => {
    useUi.setState({ canvasSystemId: system.value.id })
    const view = renderAt(`/databases/${databases.value[0].name}/datasets`, <App router={false} />)
    await screen.findByRole('region', { name: 'Page' })
    const link = within(nameIsland()).getByRole('link', { name: 'Graph' })
    expect(link).toHaveAttribute('href', base)
    fireEvent.click(link)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
  })

  it('offers no way back to a graph when no system is on the canvas', async () => {
    renderAt(`/databases/${databases.value[0].name}/datasets`, <App router={false} />)
    await screen.findByRole('region', { name: 'Page' })
    const banner = nameIsland()
    await waitFor(() => expect(within(banner).getByRole('heading', { name: databases.value[0].name })).toBeInTheDocument())
    expect(within(banner).queryByRole('link', { name: 'Graph' })).not.toBeInTheDocument()
  })

  it('titles an address no editor answers', () => {
    renderAt('/nowhere', <App router={false} />)
    expect(within(nameIsland()).getByRole('heading', { name: 'Not found' })).toBeInTheDocument()
  })

  it('puts the four menus on the name island from 1024 px', async () => {
    renderAt(base, <App router={false} />)
    const banner = await screen.findByRole('banner')
    await waitFor(() => expect(within(banner).getAllByRole('menuitem').length).toBe(4))
    expect(within(banner).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['File', 'Calculate', 'View', 'Requests'])
    expect(within(screen.getByRole('toolbar', { name: 'Frame' })).queryByRole('button', { name: 'Menus' })).not.toBeInTheDocument()
  })

  it('holds the menus in the dock below 1024 px', async () => {
    window.innerWidth = 900
    renderAt(base, <App router={false} />)
    const dock = await screen.findByRole('toolbar', { name: 'Frame' })
    expect(within(dock).getByRole('button', { name: 'Menus' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Calculate' })).not.toBeInTheDocument()
  })

  it('releases the arrangement under the case the canvas shows from the View menu', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    act(() => useUi.getState().setCanvasVariant('heavy'))
    fireEvent.keyDown(within(nameIsland()).getByRole('menuitem', { name: 'View' }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Reset layout' }))
    await waitFor(() => expect(api.releaseCards).toHaveBeenCalledWith(system.value.id, 'heavy'))
  })

  it('puts the canvas toolbar in its own island and the zoom in the dock', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    const dock = screen.getByRole('toolbar', { name: 'Frame' })
    const toolbar = await screen.findByRole('toolbar', { name: 'Canvas' })
    expect(dock.contains(toolbar)).toBe(false)
    expect(toolbar.closest('[data-clear="top"]')).not.toBeNull()
    expect(within(dock).getByRole('button', { name: 'Zoom in' })).toBeInTheDocument()
  })

  it('clears the minimap from the bottom of the graph', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    const minimap = await waitFor(() => {
      const drawn = view.container.querySelector('.react-flow__minimap')
      expect(drawn).not.toBeNull()
      return drawn as HTMLElement
    })
    expect(minimap.closest('[data-clear="bottom"]')).not.toBeNull()
  })

  it('tells how the graph is laid out under About this layout', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    expect(screen.queryByText(/One column per step away from the functional unit/)).not.toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('button', { name: 'About this layout' }), { key: 'Enter' })
    const legend = await screen.findByText(/One column per step away from the functional unit/)
    expect(legend.textContent).toMatch(/A solid outline marks the cards changed by the entries since you last looked, or by the chosen entry, in the colour of the agent that wrote them\./)
    expect(legend.textContent).toMatch(/An amber ring marks the values those entries changed\./)
    expect(legend.textContent).toMatch(/A dashed outline marks the selected card\./)
  })

  it('keeps the graph while Details holds a page of the system, and shows it in the inspector', async () => {
    const view = renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(nodes(view)).toBeGreaterThan(0)
    expect(within(screen.getByRole('complementary', { name: 'Inspector' })).getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page')
  })

  it('widens the inspector and returns it to its width', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Widen the inspector' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Widen the inspector' }))
    expect(useUi.getState().inspector).toBe('widened')
    fireEvent.click(screen.getByRole('button', { name: 'Return to width' }))
    expect(useUi.getState().inspector).toBe('open')
    expect(screen.getByRole('button', { name: 'Widen the inspector' })).toBeInTheDocument()
  })

  it('closes the inspector and leaves the graph', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Close the inspector' }))
    expect(screen.queryByRole('complementary', { name: 'Inspector' })).not.toBeInTheDocument()
    expect(nodes(view)).toBeGreaterThan(0)
  })

  it('opens a closed inspector when a card on the graph is followed', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Close the inspector' }))
    const card = view.container.querySelector('.react-flow__node a') as HTMLAnchorElement
    fireEvent.click(card)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
  })

  it('closes the inspector and shows it again on Ctrl+Alt+B', async () => {
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

  it('pins what Details holds as a chip that unpins', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Pin' }))
    const chips = screen.getByLabelText('Pinned')
    expect(within(chips).getByRole('link', { name: new RegExp(system.value.name) })).toBeInTheDocument()
    fireEvent.click(within(chips).getByRole('button', { name: `Unpin ${system.value.name}` }))
    expect(screen.queryByLabelText('Pinned')).not.toBeInTheDocument()
  })

  it('states the validation and the open requests as badges', async () => {
    renderAt(base, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('link', { name: /Valid|issue/ })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /request/ })).toHaveAttribute('href', expect.stringContaining(`${base}/requests`))
  })

  it('shows the navigation beside the dock and closes it on Esc', async () => {
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(within(screen.getByRole('toolbar', { name: 'Frame' })).getByRole('button', { name: 'Navigation' }))
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    expect(within(nav).getAllByText('Navigation')).toHaveLength(1)
    await waitFor(() => expect(within(nav).getByText('Background databases')).toBeInTheDocument())
    fireEvent.click(within(nav).getByRole('button', { name: 'Close navigation' }))
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Navigation' })).not.toBeInTheDocument())
    fireEvent.click(within(screen.getByRole('toolbar', { name: 'Frame' })).getByRole('button', { name: 'Navigation' }))
    await screen.findByRole('complementary', { name: 'Navigation' })
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Navigation' })).not.toBeInTheDocument())
  })

  it('closes only the open menu on Esc and leaves the navigation open', async () => {
    renderAt(base, <App router={false} />)
    const banner = await screen.findByRole('banner')
    await waitFor(() => expect(within(banner).getAllByRole('menuitem').length).toBe(4))
    useUi.getState().setNavOpen(true)
    await screen.findByRole('complementary', { name: 'Navigation' })
    fireEvent.keyDown(within(banner).getByRole('menuitem', { name: 'View' }), { key: 'Enter' })
    const reset = await screen.findByRole('menuitem', { name: 'Reset layout' })
    fireEvent.keyDown(reset, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menuitem', { name: 'Reset layout' })).toBeNull())
    expect(screen.getByRole('complementary', { name: 'Navigation' })).toBeInTheDocument()
  })

  it('lists product systems and background databases in the navigation sheet', async () => {
    rememberToken('?token=t')
    renderAt('/?token=t', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    expect(within(nav).getByText('Background databases')).toBeInTheDocument()
    const link = within(nav).getByText(system.value.name).closest('a')
    expect(link?.getAttribute('href')).toContain(`${base}?token=t`)
  })

  it('tells two systems of one name apart in the navigation and marks the one on the canvas', async () => {
    const name = 'Cátodo de cobre — Chile (ruta pirometalúrgica)'
    const one = { ...systems.value[0], id: 'cc344688-1f2a-4c3d-9e4f-5a6b7c8d9e0f', name }
    const two = { ...systems.value[1], id: '4b0d7d27-2a3b-4c5d-8e9f-0a1b2c3d4e5f', name }
    const only = systems.value[2]
    vi.mocked(api.systems).mockResolvedValue({ ...systems, value: [one, two, only] } as unknown as typeof systems)
    rememberToken('?token=t')
    renderAt('/?token=t', <Screens />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    await waitFor(() => expect(within(nav).getAllByText(name)).toHaveLength(2))
    act(() => useUi.getState().setCanvasSystem(one.id))
    await waitFor(() => expect(within(nav).getByText(shortHash(one.id))).toBeInTheDocument())
    expect(within(nav).getByText(shortHash(two.id))).toBeInTheDocument()
    expect(within(nav).queryByText(shortHash(only.id))).toBeNull()
    const links = [...nav.querySelectorAll('a')].filter((link) => link.textContent?.includes(name))
    expect(links).toHaveLength(2)
    const marked = links.filter((link) => link.getAttribute('aria-current') === 'true')
    expect(marked).toHaveLength(1)
    expect(within(marked[0] as HTMLElement).getByText('on the canvas')).toBeInTheDocument()
    vi.mocked(api.systems).mockResolvedValue(systems)
  })

  it('lists each database in the navigation with the five sections of its explorer', async () => {
    rememberToken('?token=t')
    renderAt('/?token=t', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    const database = databases.value[0].name
    await waitFor(() => expect(within(nav).getByRole('link', { name: database })).toBeInTheDocument())
    expect(within(nav).getByRole('link', { name: database })).toHaveAttribute('href', `/databases/${database}/datasets?token=t`)
    const group = within(nav).getByRole('link', { name: database }).parentElement!.parentElement!
    const sections: [string, string][] = [
      ['Datasets', 'datasets'],
      ['Elementary flows', 'flows'],
      ['Impact methods', 'methods'],
      ['Units', 'units'],
      ['Locations', 'locations'],
    ]
    for (const [title, section] of sections) {
      expect(within(group).getByRole('link', { name: title })).toHaveAttribute('href', `/databases/${database}/${section}?token=t`)
    }
    expect(within(nav).queryByText('search')).toBeNull()
  })

  it('wraps a long system name in the navigation and holds it whole in its title', async () => {
    const long = 'Drinking water at the consumer, CH: tap vs bottled PET (ecoinvent 3.12)'
    vi.mocked(api.systems).mockResolvedValue({ ...systems, value: [{ ...systems.value[0], name: long }] } as unknown as typeof systems)
    renderAt('/', <NavPane />)
    const link = await screen.findByRole('link', { name: long })
    const label = within(link).getByText(long)
    expect(label).toHaveAttribute('title', long)
    expect(label.className).toContain('line-clamp-2')
    vi.mocked(api.systems).mockImplementation(async () => systems)
  })

  it('closes the navigation when a link in it is followed', async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    fireEvent.click(await within(nav).findByText(system.value.name))
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Navigation' })).not.toBeInTheDocument())
  })

  it('keeps the window mounted on an address no editor answers yet', () => {
    rememberToken('?token=t')
    renderAt('/databases/fixture/nothing/none?token=t', <App router={false} />)
    expect(screen.getByText('This page has no editor for /databases/fixture/nothing/none.')).toBeInTheDocument()
  })

  it("marks a system's Simulations node while one of its runs is open", async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    fireEvent.click(within(nav).getAllByRole('button', { name: 'Expand' })[0])
    await waitFor(() => expect(within(nav).getByText('Simulations')).toBeInTheDocument())
    await waitFor(() => expect(within(nav).getByText('running')).toBeInTheDocument())
  })

  it('draws no strip of agents', async () => {
    renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.queryByLabelText('Agents')).toBeNull()
  })

  it("links a system's Results in the navigation to the results on record", async () => {
    renderAt('/', <App router={false} />)
    useUi.getState().setNavOpen(true)
    const nav = await screen.findByRole('complementary', { name: 'Navigation' })
    await waitFor(() => expect(within(nav).getByText(system.value.name)).toBeInTheDocument())
    fireEvent.click(within(nav).getAllByRole('button', { name: 'Expand' })[0])
    const results = await within(nav).findByRole('link', { name: /^Results/ })
    expect(results.getAttribute('href')).toMatch(/^\/systems\/[^/]+\/results(\?|$)/)
  })
})

describe('the narrow frame', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, canvasSystemId: null, inspector: 'open', sheetOpen: false, toolsOpen: false, navOpen: false, chosenEntry: null, since: {}, seen: {} })
  })

  afterEach(() => {
    window.innerWidth = 1024
    useLive.setState({ connection: 'closed', latest: {} })
    vi.mocked(api.log).mockResolvedValue(log as unknown as Answer<LogEntry[]>)
  })

  it('shortens the live status below 1280 px', async () => {
    const opened = () =>
      act(() => useLive.setState({ connection: 'open', latest: { [system.value.id]: log.value[0] as unknown as LogEntry } }))
    window.innerWidth = 1100
    const shortened = renderAt(base, <App router={false} />)
    const banner = await screen.findByRole('banner')
    opened()
    await waitFor(() => expect(banner).toHaveTextContent('Live'))
    expect(within(banner).queryByText(/entry #/)).toBeNull()
    shortened.unmount()
    window.innerWidth = 1440
    renderAt(base, <App router={false} />)
    const roomy = await screen.findByRole('banner')
    opened()
    await waitFor(() => expect(within(roomy).getByText(/entry #/)).toBeInTheDocument())
  })

  it('shows the build timeline from 768 px and the foot line below it', async () => {
    window.innerWidth = 1024
    const roomy = renderAt(base, <App router={false} />)
    expect(await screen.findByRole('region', { name: 'Build timeline' })).toBeInTheDocument()
    expect(screen.queryByRole('toolbar', { name: 'Build line' })).toBeNull()
    roomy.unmount()
    window.innerWidth = 700
    renderAt(base, <App router={false} />)
    expect(await screen.findByRole('toolbar', { name: 'Build line' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Build timeline' })).toBeNull()
  })

  it('opens the full log in the inspector from the timeline', async () => {
    window.innerWidth = 1024
    useUi.setState({ inspector: 'closed' })
    renderAt(base, <App router={false} />)
    fireEvent.click(await screen.findByRole('button', { name: /Full log/ }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page'))
  })

  it('opens on the graph below 768 px whatever the inspector was left as', async () => {
    window.innerWidth = 700
    useUi.setState({ inspector: 'open' })
    const view = renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  })

  it('opens the full log from the foot line', async () => {
    window.innerWidth = 700
    renderAt(base, <App router={false} />)
    const line = await screen.findByRole('toolbar', { name: 'Build line' })
    fireEvent.click(within(line).getByRole('button', { name: /^created/ }))
    await waitFor(() =>
      expect(within(screen.getByRole('complementary', { name: 'Inspector' })).getByRole('link', { name: 'Activity' })).toHaveAttribute('aria-current', 'page'),
    )
  })

  it('leaves Calculate off the foot line while the canvas shows an older entry', async () => {
    window.innerWidth = 700
    vi.mocked(api.log).mockResolvedValue({ ...log, value: [log.value[0], { ...log.value[0], seq: 2, result_hash: 'b'.repeat(64), message: 'updated the frame' }] } as unknown as Answer<LogEntry[]>)
    const view = renderAt(base, <Screens />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    act(() => useUi.getState().chooseEntry({ systemId: system.value.id, seq: 1, hash: log.value[0].result_hash }))
    const line = await screen.findByRole('toolbar', { name: 'Build line' })
    expect(within(line).queryByRole('button', { name: 'Calculate an impact result' })).toBeNull()
  })

  it('shows and hides the sheet on Ctrl+Alt+B, closing the canvas tools with it and leaving the inspector as it was', async () => {
    window.innerWidth = 700
    useUi.setState({ inspector: 'closed' })
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    expect(await screen.findByRole('toolbar', { name: 'Canvas' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    expect(await screen.findByRole('complementary', { name: 'Inspector' })).toBeInTheDocument()
    expect(screen.queryByRole('toolbar', { name: 'Canvas' })).toBeNull()
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull())
    expect(screen.queryByRole('toolbar', { name: 'Canvas' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    expect(await screen.findByRole('toolbar', { name: 'Canvas' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Canvas tools' })).toHaveAttribute('aria-pressed', 'true')
    expect(useUi.getState().inspector).toBe('closed')
  })

  it('opens the sheet when a card is followed, closing the canvas tools with it', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    expect(await screen.findByRole('toolbar', { name: 'Canvas' })).toBeInTheDocument()
    fireEvent.click(view.container.querySelector('.react-flow__node a') as HTMLAnchorElement)
    await waitFor(() =>
      expect(within(screen.getByRole('complementary', { name: 'Inspector' })).getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'),
    )
    expect(screen.queryByRole('toolbar', { name: 'Canvas' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Canvas tools' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('calls the canvas tools from the foot line, keeps Calculate there and closes the sheet with them', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    expect(screen.queryByRole('toolbar', { name: 'Canvas' })).toBeNull()
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    expect(await screen.findByRole('complementary', { name: 'Inspector' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    const bar = await screen.findByRole('toolbar', { name: 'Canvas' })
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull())
    expect(within(bar).queryByRole('button', { name: 'Calculate an impact result' })).toBeNull()
    expect(within(screen.getByRole('toolbar', { name: 'Build line' })).getByRole('button', { name: 'Calculate an impact result' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument()
  })

  it('closes the shown sheet on Esc', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    expect(await screen.findByRole('complementary', { name: 'Inspector' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull())
  })

  it('closes the canvas tools on Esc', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    expect(await screen.findByRole('toolbar', { name: 'Canvas' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('toolbar', { name: 'Canvas' })).toBeNull())
    expect(screen.getByRole('button', { name: 'Canvas tools' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
  })

  it('closes only the open canvas menu on Esc and leaves the navigation and the tools open', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    await screen.findByRole('toolbar', { name: 'Canvas' })
    useUi.getState().setNavOpen(true)
    await screen.findByRole('complementary', { name: 'Navigation' })
    fireEvent.keyDown(screen.getByRole('button', { name: 'More canvas options' }), { key: 'Enter' })
    const reset = await screen.findByRole('menuitem', { name: 'Reset layout' })
    fireEvent.keyDown(reset, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menuitem', { name: 'Reset layout' })).toBeNull())
    expect(screen.getByRole('complementary', { name: 'Navigation' })).toBeInTheDocument()
    expect(screen.getByRole('toolbar', { name: 'Canvas' })).toBeInTheDocument()
  })

  it('leaves Esc typed into a field to the field', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    await screen.findByRole('complementary', { name: 'Inspector' })
    useUi.getState().setNavOpen(true)
    await screen.findByRole('complementary', { name: 'Navigation' })
    const field = document.createElement('input')
    document.body.append(field)
    fireEvent.keyDown(field, { key: 'Escape' })
    field.remove()
    expect(screen.getByRole('complementary', { name: 'Inspector' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Navigation' })).toBeInTheDocument()
  })

  it('names the result held in a closed sheet when the window narrows from 1024 to 700 px', async () => {
    window.innerWidth = 1024
    const method = encodeURIComponent(firstMethodOf(impact.value).impact_method)
    renderAt(`${base}/results/sankey?impact_method=${method}`, <App router={false} />)
    const roomy = await screen.findByRole('complementary', { name: 'Inspector' })
    await waitFor(() => expect(within(roomy).getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'))
    expect(screen.queryByRole('toolbar', { name: 'Build line' })).toBeNull()
    act(() => resizePage(700))
    const line = await screen.findByRole('toolbar', { name: 'Build line' })
    expect(screen.queryByRole('complementary', { name: 'Inspector' })).toBeNull()
    const held = within(line).getByRole('button', { name: `Results of: ${system.value.name}` })
    fireEvent.click(held)
    await waitFor(() =>
      expect(within(screen.getByRole('complementary', { name: 'Inspector' })).getByRole('link', { name: 'Details' })).toHaveAttribute('aria-current', 'page'),
    )
  })

  it('keeps the sheet out of the row the build line takes, open and widened', async () => {
    window.innerWidth = 700
    const view = renderAt(`${base}/general`, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true, altKey: true })
    const sheet = await screen.findByRole('complementary', { name: 'Inspector' })
    const lineRows = rowsOf(screen.getByRole('toolbar', { name: 'Build line' }))
    expect(rowsOf(sheet)).toEqual([2])
    expect(rowsOf(sheet).filter((row) => lineRows.includes(row))).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Widen the inspector' }))
    const widened = screen.getByRole('complementary', { name: 'Inspector' })
    expect(rowsOf(widened)).toEqual([1, 2])
    expect(rowsOf(widened).filter((row) => lineRows.includes(row))).toEqual([])
  })

  it('holds the zoom and the canvas toolbar in one island below 768 px', async () => {
    window.innerWidth = 700
    const view = renderAt(base, <App router={false} />)
    await waitFor(() => expect(nodes(view)).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: 'Canvas tools' }))
    const zoom = await screen.findByRole('button', { name: 'Zoom in' })
    const bar = screen.getByRole('toolbar', { name: 'Canvas' })
    const island = zoom.closest('.rounded-xl') as HTMLElement
    expect(island).not.toBeNull()
    expect(island.contains(bar)).toBe(true)
  })
})
