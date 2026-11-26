import { fireEvent, screen, within } from '@testing-library/react'
import type { ServerInfo, SystemRead } from '@/api/types'
import { api } from '@/api/client'
import { useUi, type EditorTab } from '@/store/ui'
import { Dock } from '@/window/Dock'
import { NameIsland } from '@/window/NameIsland'
import { PinChips } from '@/window/PinChips'
import { FieldGrid } from '@/window/FieldGrid'
import server from './fixtures/server.json'
import system from './fixtures/system.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      server: vi.fn(async () => server),
      system: vi.fn(async () => system),
    },
  }
})

const LONG = 'Drinking water at the consumer, CH: tap vs bottled PET (ecoinvent 3.12)'
const id = system.value.id

describe('the frame', () => {
  beforeEach(() => {
    useUi.setState({ pinned: [], details: null, lastDetails: null, theme: 'light', inspector: 'open', sheetOpen: false, navOpen: false })
  })

  it('links the logo to the list of product systems', () => {
    renderAt('/', <Dock menus={null} />)
    const logo = screen.getByRole('link', { name: 'EcoSemantic: all product systems' })
    expect(logo.getAttribute('href')).toMatch(/^\/(\?|$)/)
  })

  it('turns the dark theme on and off from the dock', () => {
    renderAt('/', <Dock menus={null} />)
    const button = screen.getByRole('button', { name: 'Dark theme' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(button)
    expect(useUi.getState().theme).toBe('dark')
    expect(button).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(button)
    expect(useUi.getState().theme).toBe('light')
  })

  it('names the connected chatbot on the name island, and nothing when none introduced itself', async () => {
    const view = renderAt('/', <NameIsland menus={null} systemId={id} />)
    expect(await screen.findByText(`Connected: ${server.client.name}`)).toBeInTheDocument()
    view.unmount()
    vi.mocked(api.server).mockResolvedValue({ ...server, client: null } as unknown as ServerInfo)
    renderAt('/', <NameIsland menus={null} systemId={id} />)
    expect(await screen.findByRole('heading', { name: (named: string) => named.startsWith(system.value.name) })).toBeInTheDocument()
    expect(screen.queryByText(/Connected:/)).not.toBeInTheDocument()
  })

  it('wraps a long system name on two lines and holds it whole in its title', async () => {
    vi.mocked(api.system).mockResolvedValue({ ...system, value: { ...system.value, name: LONG } } as SystemRead)
    renderAt('/', <NameIsland menus={null} systemId={id} />)
    const heading = await screen.findByRole('heading', { name: (named: string) => named.startsWith(LONG) })
    expect(heading).toHaveClass('line-clamp-2')
    expect(heading).toHaveAttribute('title', LONG)
  })

  it('links the system’s name to its General information, marked by an info icon', async () => {
    vi.mocked(api.system).mockResolvedValue(system as SystemRead)
    renderAt(`/systems/${id}/general`, <NameIsland menus={null} systemId={id} />)
    const heading = await screen.findByRole('heading', { name: (named: string) => named.startsWith(system.value.name) })
    const link = within(heading).getByRole('link')
    expect(link).toHaveAccessibleName(/Product system details$/)
    expect(link).toHaveAttribute('href', `/systems/${id}/general`)
    const mark = within(link).getByRole('img', { name: 'Product system details' })
    expect(mark).toHaveAttribute('title', 'Product system details')
  })

  it('unpins a chip', () => {
    const tab: EditorTab = { id: `system:${id}`, kind: 'system', title: 'Cátodo de cobre', path: `/systems/${id}` }
    useUi.setState({ pinned: [tab], details: tab })
    renderAt('/', <PinChips />)
    const chips = screen.getByLabelText('Pinned')
    expect(within(chips).getByRole('link', { name: tab.title })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(within(chips).getByRole('button', { name: `Unpin ${tab.title}` }))
    expect(useUi.getState().pinned).toEqual([])
  })

  it('a detail’s value is text', () => {
    renderAt('/', <FieldGrid rows={[{ label: 'Reference product', value: 'widget' }]} />)
    const value = screen.getByText('widget')
    expect(value.tagName).toBe('DD')
    expect(value).toHaveClass('break-words')
    expect(value.className).not.toContain('border')
    expect(value.className).not.toContain('rounded')
    expect(value.className).not.toContain('bg-background')
    expect(value.className).not.toContain('min-h-7')
    expect(value.className).not.toContain('px-2')
  })
})
