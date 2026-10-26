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
