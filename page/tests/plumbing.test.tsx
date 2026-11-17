import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useLive } from '@/api/stream'
import type { LogEntry } from '@/api/types'
import { OpenTrails } from '@/activity/OpenTrails'
import { Histogram } from '@/editors/results/figures/Histogram'
import { useUi } from '@/store/ui'
import { DataTable } from '@/window/DataTable'
import { LiveStatus } from '@/window/LiveStatus'
import log from './fixtures/log.json'
import openTrail from './fixtures/open_trail.json'

const agentsAnswer = vi.hoisted(() => ({ value: [] as unknown[] }))

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      agents: vi.fn(async () => ({ value: agentsAnswer.value, hint: null, view_url: null })),
      openTrail: vi.fn(async () => openTrail),
    },
  }
})

it('says when the latest entry of the system on the canvas was written, with the instant in its title', () => {
  const minutesAgo = new Date(Date.now() - 5 * 60_000).toISOString()
  useUi.setState({ canvasSystemId: 's1' })
  useLive.setState({ connection: 'open', latest: { s1: { ...(log.value[0] as LogEntry), timestamp: minutesAgo } } })
  render(<LiveStatus />)
  const when = screen.getByText(/5 min ago/)
  expect(when.getAttribute('title')).toBe(minutesAgo)
  useLive.setState({ connection: 'closed', latest: {} })
  useUi.setState({ canvasSystemId: null })
})

it('lets a table cell wrap rather than widen the panel', () => {
  const { container } = render(<DataTable columns={[{ key: 'a', header: 'A', render: (r: string) => r }]} rows={['a long value']} rowKey={(r) => r} />)
  const cell = container.querySelector('td')!
  expect(cell.className).not.toContain('whitespace-nowrap')
  expect(cell.className).toContain('break-words')
})

it('lets a table header wrap rather than widen the panel to its longest header', () => {
  const { container } = render(<DataTable columns={[{ key: 'score', header: 'Result [kg CO2-Eq]', align: 'right', render: (r: string) => r }]} rows={['1']} rowKey={(r) => r} />)
  expect(container.querySelector('th')!.className).not.toContain('whitespace-nowrap')
})

it('breaks a machine string in a table cell anywhere rather than widen the panel', () => {
  const { container } = render(<DataTable columns={[{ key: 'f', header: 'Formula', render: (r: string) => <code>{r}</code> }]} rows={['oxygen_per_kg_conc*conc_per_kg_anode']} rowKey={(r) => r} />)
  expect(container.querySelector('td')!.className).toContain('[&_code]:[overflow-wrap:anywhere]')
})

it('writes the histogram axis and its close markers as page text, never scaled with the figure or over the bars', () => {
  const samples = Array.from({ length: 50 }, (_, i) => 10 + i / 10)
  const { container } = render(<Histogram samples={samples} mean={12.4} median={12.45} percentiles={[10.1, 14.8]} medianCi95={[12.2, 12.6]} unit="kg" />)
  expect(container.querySelectorAll('svg text')).toHaveLength(0)
  const axis = within(screen.getByLabelText('Axis'))
  expect(axis.getByText('10')).toBeInTheDocument()
  expect(axis.getByText(/kg$/)).toBeInTheDocument()
  const legend = within(screen.getByRole('list', { name: 'Markers' }))
  expect(legend.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['mean', 'median', '2.5th pct', '97.5th pct'])
})

it('says when an agent was last active once its trail goes quiet', async () => {
  const hourAgo = new Date(Date.now() - 60 * 60_000).toISOString()
  agentsAnswer.value = [{ agent: 'a1', client: 'claude', origin: 'agent', first_call_at: hourAgo, last_call_at: hourAgo, calls: 1, product_system_id: 's1' }]
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <OpenTrails systemId="s1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('a1 · last active 1 h ago')).toBeInTheDocument()
  expect(screen.queryByText(/work in progress/)).toBeNull()
})

it('stacks each row as label and value when its columns do not fit, and returns to columns when they do', () => {
  const observers: (() => void)[] = []
  const original = globalThis.ResizeObserver
  globalThis.ResizeObserver = class {
    constructor(callback: ResizeObserverCallback) {
      observers.push(() => callback([], this as unknown as ResizeObserver))
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
  const room = { value: 373 }
  const clientWidth = vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (this: Element) {
    return this.tagName === 'DIV' ? room.value : 0
  })
  // the eight columns of the ready-mix inputs need 764 px
  const scrollWidth = vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (this: Element) {
    return this.tagName === 'TABLE' ? 764 : 0
  })
  const columns = [
    { key: 'flow', header: 'Flow', render: (r: string) => r },
    { key: 'unit', header: 'Unit', render: () => 'kilogram' },
  ]
  const { container } = render(<DataTable columns={columns} rows={['sand']} rowKey={(r) => r} />)
  const table = container.querySelector('table')!
  expect(table.dataset.stacked).toBe('true')
  expect(container.querySelector('td')!.dataset.label).toBe('Flow')
  room.value = 800
  act(() => observers.forEach((o) => o()))
  expect(table.dataset.stacked).toBeUndefined()
  clientWidth.mockRestore()
  scrollWidth.mockRestore()
  globalThis.ResizeObserver = original
})

// a box the browser reports as `at` wide, and a table whose headers carry `foldsAt` so that its
// layout is `folded` px wide below the box width `unfoldsAt` and `unfolded` px wide from there up
function measuredBox({ at, folded, unfolded, foldsAt, unfoldsAt }: { at: number; folded: number; unfolded: number; foldsAt: string; unfoldsAt: number }) {
  const room = { value: at }
  let observers: (() => void)[] = []
  const original = globalThis.ResizeObserver
  globalThis.ResizeObserver = class {
    private entry: () => void
    constructor(callback: ResizeObserverCallback) {
      this.entry = () => callback([], this as unknown as ResizeObserver)
      observers = [...observers, this.entry]
    }
    observe() {}
    unobserve() {}
    disconnect() {
      observers = observers.filter((entry) => entry !== this.entry)
    }
  } as unknown as typeof ResizeObserver
  const clientWidth = vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (this: Element) {
    return this.tagName === 'DIV' ? room.value : 0
  })
  const scrollWidth = vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (this: Element) {
    if (this.tagName !== 'TABLE') return 0
    const folds = room.value < unfoldsAt && [...this.querySelectorAll('th')].some((th) => th.className.includes(foldsAt))
    return folds ? folded : unfolded
  })
  const resize = (width: number) => {
    room.value = width
    act(() => observers.forEach((entry) => entry()))
  }
  const restore = () => {
    clientWidth.mockRestore()
    scrollWidth.mockRestore()
    globalThis.ResizeObserver = original
  }
  return { resize, restore }
}

const twoColumns = [
  { key: 'flow', header: 'Flow', render: (r: string) => r },
  { key: 'note', header: 'Note', folds: true, render: () => 'a folded note' },
]

it('keeps a table in columns while its folded layout fits a box its columns need more than', () => {
  const box = measuredBox({ at: 551, folded: 380, unfolded: 900, foldsAt: '@3xl:table-cell', unfoldsAt: 736 })
  const { container } = render(<DataTable columns={twoColumns} rows={['sand']} rowKey={(r) => r} unfoldAt="3xl" />)
  expect(container.querySelector('table')!.dataset.stacked).toBeUndefined()
  expect(container.querySelector('tbody tr')!.className).not.toContain('block')
  box.restore()
})

it('returns a stacked table to columns once its folded layout fits a box that is narrow again', () => {
  const box = measuredBox({ at: 1000, folded: 380, unfolded: 1200, foldsAt: '@lg:table-cell', unfoldsAt: 480 })
  const { container } = render(<DataTable columns={twoColumns} rows={['sand']} rowKey={(r) => r} />)
  expect(container.querySelector('table')!.dataset.stacked).toBe('true')
  box.resize(400)
  expect(container.querySelector('table')!.dataset.stacked).toBeUndefined()
  box.restore()
})

it('stacks a table whose box grows past its fold width without reaching the width its columns need', () => {
  const box = measuredBox({ at: 343, folded: 400, unfolded: 900, foldsAt: '@lg:table-cell', unfoldsAt: 480 })
  const { container } = render(<DataTable columns={twoColumns} rows={['sand']} rowKey={(r) => r} />)
  expect(container.querySelector('table')!.dataset.stacked).toBe('true')
  box.resize(583)
  expect(container.querySelector('table')!.dataset.stacked).toBe('true')
  box.restore()
})

it('folds a column at the container breakpoint the table names', () => {
  const { container } = render(<DataTable columns={twoColumns} rows={['sand']} rowKey={(r) => r} unfoldAt="3xl" />)
  const header = container.querySelectorAll('th')[1]
  expect(header).toHaveClass('hidden', '@3xl:table-cell')
  expect(header).not.toHaveClass('@lg:table-cell')
  const folded = container.querySelectorAll('td')[0].children
  expect(folded[0]).toHaveClass('@3xl:hidden')
})

it('wraps a folded line inside a right-aligned column, and holds the number it carries on one line', () => {
  const columns = [
    { key: 'share', header: 'Contribution', align: 'right' as const, render: (r: string) => r },
    { key: 'product', header: 'Reference product', folds: true, render: () => 'electricity, high voltage' },
    { key: 'amount', header: 'Amount', align: 'right' as const, folds: true, render: () => '1,204.5' },
  ]
  const { container } = render(<DataTable columns={columns} rows={['29.1 %']} rowKey={(r) => r} />)
  const lines = [...container.querySelectorAll('td')[0].children].filter((el) => el.className.includes('@lg:hidden'))
  expect(lines[0]).toHaveClass('whitespace-normal')
  expect(lines[0].querySelectorAll('span')[1]).not.toHaveClass('whitespace-nowrap')
  expect(lines[1]).toHaveClass('whitespace-normal')
  expect(lines[1].querySelectorAll('span')[1]).toHaveClass('whitespace-nowrap')
})
