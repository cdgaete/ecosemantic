import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { Link, MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import type { LogEntry, ProductSystem } from '@/api/types'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { READABLE_ZOOM } from '@/editors/graph/layout'
import { paths } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { ISLAND_GAP, useClearance } from '@/window/clearance'
import { useSheetTop } from '@/window/cover'
import { Slot, SlotsProvider } from '@/window/slots'
import { runCanvas } from '@/window/shortcuts'
import { CARD, layoutAnswer } from './placements'
import log from './fixtures/log.json'
import system from './fixtures/system.json'

type Viewport = { x: number; y: number; zoom: number }
type Moves = {
  onMoveStart?: (event: MouseEvent | null, viewport: Viewport) => void
  onMove?: (event: MouseEvent | null, viewport: Viewport) => void
  onNodeDragStart?: () => void
}

const moved = vi.hoisted(() => vi.fn())
const measured = vi.hoisted(() => ({ value: true }))
const flowProps = vi.hoisted(() => ({ current: {} as Moves }))
const canvas = vi.hoisted(() => ({ width: 1024, height: 768 }))
const viewport = vi.hoisted(() => ({ x: 0, y: 0, zoom: 1 }))
const boxes = vi.hoisted(() => ({
  all: { x: 0, y: 0, width: 400, height: 300 },
  reference: { x: 120, y: 40, width: 280, height: 220 },
  both: { x: 120, y: 40, width: 280, height: 220 },
}))

vi.mock('@xyflow/react', async (importOriginal) => {
  const original = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...original,
    ReactFlow: (props: Record<string, unknown>) => {
      flowProps.current = props as unknown as Moves
      return createElement(original.ReactFlow as never, props as never)
    },
    useReactFlow: () => ({
      ...original.useReactFlow(),
      setViewport: moved,
      getViewport: () => viewport,
      getNodesBounds: (asked: unknown[]) => {
        if (asked.length === 0) return { x: 0, y: 0, width: 0, height: 0 }
        if (asked.every((item) => typeof item === 'string')) return asked.length === 1 ? boxes.reference : boxes.both
        return boxes.all
      },
    }),
    useStore: (selector: (state: Record<string, unknown>) => unknown) =>
      original.useStore((state) => selector({ ...(state as unknown as Record<string, unknown>), width: canvas.width, height: canvas.height })),
    useNodesInitialized: () => measured.value,
  }
})

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, layout: vi.fn() } }
})

const doc = system.value as ProductSystem
const VIEW: Viewport = { x: 0, y: 0, zoom: 1 }

function DetailsLinks() {
  return (
    <nav>
      <Link to={paths.process(doc.id, 'widget')}>widget details</Link>
      <Link to={paths.process(doc.id, 'frame')}>frame details</Link>
    </nav>
  )
}

function shifted() {
  const answer = layoutAnswer(doc)
  return { ...answer, value: { ...answer.value, cards: answer.value.cards.map((card, at) => (at === 0 ? { ...card, x: card.x + 120 } : card)) } }
}

function entryAt(seq: number, exchangeId: string): LogEntry {
  return { ...(log.value[0] as LogEntry), seq, changes: [{ op: 'add', entity: 'exchange', id: exchangeId, field: null, before: null, after: null }] } as LogEntry
}

const TO_WIDGET = '73b7d6fd-7d08-53d6-bd18-093e6cd44574'

function Graph({ client, product = doc, latest = null, at = '/' }: { client: QueryClient; product?: ProductSystem; latest?: LogEntry | null; at?: string }) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <TooltipProvider>
          <SlotsProvider>
            <Slot name="tools" />
            <Slot name="view" />
            <Slot name="minimap" />
            <Slot name="notice" />
            <ModelGraph system={product} latest={latest} />
            <DetailsLinks />
          </SlotsProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

async function arranged(client: QueryClient): Promise<void> {
  vi.mocked(api.layout).mockImplementation(async () => shifted())
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['layout', doc.id] })
  })
}

function panned(to: Viewport = { ...VIEW, x: -40 }): void {
  act(() => {
    flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW)
    flowProps.current.onMove?.(new MouseEvent('mousemove'), to)
  })
}

beforeEach(() => {
  moved.mockClear()
  measured.value = true
  canvas.width = 1024
  canvas.height = 768
  viewport.x = 0
  viewport.y = 0
  viewport.zoom = 1
  boxes.all = { x: 0, y: 0, width: 400, height: 300 }
  boxes.reference = { x: 120, y: 40, width: 280, height: 220 }
  boxes.both = { x: 120, y: 40, width: 280, height: 220 }
  useClearance.setState({ clearance: { top: ISLAND_GAP, right: ISLAND_GAP, bottom: ISLAND_GAP, left: ISLAND_GAP } })
  vi.mocked(api.layout).mockImplementation(async () => layoutAnswer(doc))
})

it('fits the drawing clear of the islands, at no more than full size', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  measured.value = false
  const client = new QueryClient()
  const view = render(<Graph client={client} />)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(moved).not.toHaveBeenCalled()
  measured.value = true
  view.rerender(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  expect(moved.mock.calls[0][0]).toEqual({ x: 354 - 200, y: 379 - 150, zoom: 1 })
})

it('never fits the whole drawing below the readable zoom, holding the reference card at the right of the clear area', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  boxes.all = { x: 0, y: 0, width: 2260, height: 370 }
  boxes.reference = { x: 1990, y: 90, width: 270, height: 190 }
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  const [view] = moved.mock.calls[0]
  expect(view.zoom).toBe(0.5)
  expect(view.x + (boxes.reference.x + boxes.reference.width) * view.zoom).toBeCloseTo(640)
  expect(view.y).toBeCloseTo(379 - 185 * 0.5)
})

it('fits again when an island opens while it follows', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => useClearance.getState().setClearance({ top: 122, right: 424, bottom: 132, left: 68 }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][0]).toEqual({ x: 334 - 200, y: 379 - 150, zoom: 1 })
})

it('moves nothing when an island opens while following is paused', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  panned()
  await screen.findByRole('button', { name: 'Follow the build' })
  act(() => useClearance.getState().setClearance({ top: 122, right: 424, bottom: 132, left: 68 }))
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(moved).toHaveBeenCalledTimes(1)
})

it('keeps the zoom and the centre of the view when the canvas is resized while following is paused', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  viewport.x = 10
  viewport.y = 20
  viewport.zoom = 0.8
  const client = new QueryClient()
  const view = render(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  panned()
  await screen.findByRole('button', { name: 'Follow the build' })
  canvas.width = 700
  view.rerender(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][0]).toEqual({ x: 10 + (192 - 354), y: 20, zoom: 0.8 })
})

it('fits again, moving, whenever the arrangement changes while it follows', async () => {
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  await arranged(client)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][1]).toMatchObject({ duration: 250 })
})

it('stops following on a move the person makes, and follows again from the toolbar', async () => {
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
  panned()
  const follow = await screen.findByRole('button', { name: 'Follow the build' })
  await arranged(client)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(moved).toHaveBeenCalledTimes(1)
  fireEvent.click(follow)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('leaves following on for a press that moves nothing', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => {
    flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW)
    flowProps.current.onMove?.(new MouseEvent('mousemove'), VIEW)
  })
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('stops following at the first step of a move that changes the view, and frames nothing while that move lasts', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => {
    flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW)
    flowProps.current.onMove?.(new MouseEvent('mousemove'), { ...VIEW, x: -40 })
  })
  await screen.findByRole('button', { name: 'Follow the build' })
  act(() => useClearance.getState().setClearance({ top: 122, right: 424, bottom: 132, left: 68 }))
  await new Promise((resolve) => setTimeout(resolve, 50))
  act(() => flowProps.current.onMove?.(new MouseEvent('mousemove'), { ...VIEW, x: -80 }))
  expect(moved).toHaveBeenCalledTimes(1)
})

it('keeps following through a move the page makes itself', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => {
    flowProps.current.onMoveStart?.(null, VIEW)
    flowProps.current.onMove?.(null, { ...VIEW, x: -40 })
  })
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('stops following when the person drags a card', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => flowProps.current.onNodeDragStart?.())
  expect(await screen.findByRole('button', { name: 'Follow the build' })).toBeInTheDocument()
})

it('stops following when the person zooms with the view tools', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
  expect(await screen.findByRole('button', { name: 'Follow the build' })).toBeInTheDocument()
})

it('follows another system the canvas switches to, even when following was paused', async () => {
  const client = new QueryClient()
  const view = render(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  panned()
  await screen.findByRole('button', { name: 'Follow the build' })
  view.rerender(<Graph client={client} product={{ ...doc, id: 'another' }} />)
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument())
})

it('frames the card a new entry changed, and fits the whole drawing once the build goes quiet', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
    boxes.all = { x: 0, y: 0, width: 2260, height: 370 }
    boxes.reference = { x: 120, y: 40, width: 280, height: 220 }
    const client = new QueryClient()
    const view = render(<Graph client={client} latest={entryAt(1, TO_WIDGET)} />)
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    // the entry already there when the canvas opened is not framed
    expect(moved.mock.calls[0][0].zoom).toBe(0.5)
    view.rerender(<Graph client={client} latest={entryAt(2, TO_WIDGET)} />)
    // the changed card is framed; whether its supplier joins it depends on its room in the clear area
    await waitFor(() => expect(moved.mock.calls.at(-1)?.[0]).toEqual({ x: 354 - 260, y: 379 - 150, zoom: 1 }))
    expect(moved.mock.calls.at(-1)?.[1]).toMatchObject({ duration: 250 })
    const framed = moved.mock.calls.length
    act(() => vi.advanceTimersByTime(10_000))
    await waitFor(() => expect(moved.mock.calls.length).toBeGreaterThan(framed))
    expect(moved.mock.calls.at(-1)?.[0].zoom).toBe(0.5)
  } finally {
    vi.useRealTimers()
  }
})

it('frames nothing while following is paused', async () => {
  const client = new QueryClient()
  const view = render(<Graph client={client} latest={entryAt(1, TO_WIDGET)} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  panned()
  await screen.findByRole('button', { name: 'Follow the build' })
  view.rerender(<Graph client={client} latest={entryAt(2, TO_WIDGET)} />)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(moved).toHaveBeenCalledTimes(1)
})

it('names Follow the build in words from 1280 px and by its icon below', async () => {
  window.innerWidth = 1440
  try {
    const wide = render(<Graph client={new QueryClient()} />)
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    panned()
    const named = await screen.findByRole('button', { name: 'Follow the build' })
    expect(named.textContent).toContain('Follow the build')
    wide.unmount()
    window.innerWidth = 1100
    render(<Graph client={new QueryClient()} />)
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
    panned()
    const icon = await screen.findByRole('button', { name: 'Follow the build' })
    expect(icon.textContent).toBe('')
    expect(icon).toHaveAccessibleName('Follow the build')
  } finally {
    window.innerWidth = 1024
  }
})

it('centres a process it is asked to show in the clear area, at the zoom it has, and stops following', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => runCanvas({ show: 'widget' }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  const card = layoutAnswer(doc).value.cards.find((c) => c.code === 'widget')!
  const [view, options] = moved.mock.calls[1]
  expect(view.zoom).toBe(1)
  expect(view.x + (card.x + card.width / 2) * view.zoom).toBeCloseTo(354)
  expect(view.y + (card.y + card.height / 2) * view.zoom).toBeCloseTo(379)
  expect(options).toMatchObject({ duration: 250 })
  expect(await screen.findByRole('button', { name: /Follow the build/ })).toBeInTheDocument()
})

it('focuses the reference process clear of the islands, at no more than full size', async () => {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  boxes.reference = { x: 120, y: 40, width: 280, height: 220 }
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => runCanvas('focus'))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][0]).toEqual({ x: 354 - 260, y: 379 - 150, zoom: 1 })
})

function wideDrawing(): void {
  useClearance.setState({ clearance: { top: 122, right: 384, bottom: 132, left: 68 } })
  boxes.all = { x: 0, y: 0, width: 2260, height: 370 }
  boxes.reference = { x: 1990, y: 90, width: 270, height: 190 }
}

it('shows the whole drawing below the readable zoom when the person asks to fit the graph', async () => {
  wideDrawing()
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  expect(moved.mock.calls[0][0].zoom).toBe(READABLE_ZOOM)
  fireEvent.click(screen.getByRole('button', { name: 'Fit the graph' }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  const [view] = moved.mock.calls[1]
  expect(view.zoom).toBeCloseTo(572 / 2260)
  expect(view.x).toBeCloseTo(68 + 572 / 2 - 1130 * view.zoom)
  expect(view.y).toBeCloseTo(122 + 514 / 2 - 185 * view.zoom)
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('holds the whole drawing when an island opens after the person fit the graph', async () => {
  wideDrawing()
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole('button', { name: 'Fit the graph' }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  act(() => useClearance.getState().setClearance({ top: 122, right: 424, bottom: 132, left: 68 }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(3))
  const [view] = moved.mock.calls[2]
  expect(view.zoom).toBeCloseTo(532 / 2260)
  expect(view.zoom).toBeLessThan(READABLE_ZOOM)
  expect(view.x + (boxes.all.x + boxes.all.width) * view.zoom).toBeLessThanOrEqual(1024 - 424)
})

it('fits at the readable zoom again from Follow the build once a move paused following', async () => {
  wideDrawing()
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole('button', { name: 'Fit the graph' }))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][0].zoom).toBeLessThan(READABLE_ZOOM)
  panned()
  const follow = await screen.findByRole('button', { name: 'Follow the build' })
  fireEvent.click(follow)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(3))
  expect(moved.mock.calls[2][0].zoom).toBe(READABLE_ZOOM)
  expect(moved.mock.calls[2][0].x + (boxes.reference.x + boxes.reference.width) * READABLE_ZOOM).toBeCloseTo(1024 - 384)
})

it('fits the whole drawing from the shortcut that fits the graph', async () => {
  wideDrawing()
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
  act(() => runCanvas('fit'))
  await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
  expect(moved.mock.calls[1][0].zoom).toBeCloseTo(572 / 2260)
})

describe('the sheet the narrow inspector opens over the canvas', () => {
  const cards = layoutAnswer(doc).value.cards
  const widget = cards.find((card) => card.code === 'widget')!
  const frame = cards.find((card) => card.code === 'frame')!
  const sheetTop = 300
  // the clear area keeps the islands' gap, and its lower edge stays that gap above the sheet
  const left = ISLAND_GAP
  const bottom = sheetTop - ISLAND_GAP

  async function drawn(at: string): Promise<void> {
    render(<Graph client={new QueryClient()} at={at} />)
    await waitFor(() => expect(moved).toHaveBeenCalled())
    panned()
    await screen.findByRole('button', { name: 'Follow the build' })
    moved.mockClear()
  }

  beforeEach(() => {
    window.innerWidth = 700
    useClearance.setState({ clearance: { top: ISLAND_GAP, right: ISLAND_GAP, bottom: ISLAND_GAP, left: ISLAND_GAP } })
    useSheetTop.setState({ sheetTop })
    useUi.setState({ inspector: 'open', sheetOpen: false, chosenProcess: null })
  })

  afterEach(() => {
    window.innerWidth = 1024
    useSheetTop.setState({ sheetTop: null })
    useUi.setState({ sheetOpen: false })
  })

  it('pans just enough, at the zoom it holds, to hold the chosen card header above the sheet', async () => {
    viewport.x = left
    viewport.y = 100
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    expect(moved.mock.calls[0][0]).toEqual({ x: left, y: bottom - (widget.y + CARD.header_height), zoom: 1 })
    expect(moved.mock.calls[0][1]).toMatchObject({ duration: 250 })
  })

  it('leaves a card header the sheet does not cover where it is', async () => {
    viewport.x = left
    viewport.y = -200
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(moved).not.toHaveBeenCalled()
  })

  it('forces no pan while the sheet covers the canvas whole', async () => {
    useSheetTop.setState({ sheetTop: ISLAND_GAP })
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true, inspector: 'widened' }))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(moved).not.toHaveBeenCalled()
  })

  it('leaves the canvas roomy from 768 px whatever the sheet state', async () => {
    window.innerWidth = 1024
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(moved).not.toHaveBeenCalled()
  })

  it('does not recentre while the person pans, or when the sheet is measured again after it moved', async () => {
    viewport.x = left
    viewport.y = 100
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    panned()
    act(() => useSheetTop.setState({ sheetTop: sheetTop + 60 }))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(moved).toHaveBeenCalledTimes(1)
  })

  it('pans again to the same card when the sheet is reopened on it', async () => {
    viewport.x = left
    viewport.y = 100
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    act(() => useUi.setState({ sheetOpen: false }))
    moved.mockClear()
    viewport.y = 300
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    expect(moved.mock.calls[0][0]).toEqual({ x: left, y: bottom - (widget.y + CARD.header_height), zoom: 1 })
  })

  it('pans to the card a switch of the details names, and to none a page names no card of', async () => {
    viewport.x = left
    viewport.y = 300
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('link', { name: 'frame details' }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(2))
    expect(moved.mock.calls[1][0]).toEqual({ x: left, y: bottom - (frame.y + CARD.header_height), zoom: 1 })
  })

  function titled(box: { left: number; right: number; top: number; bottom: number }): () => void {
    const original = HTMLElement.prototype.getBoundingClientRect
    const spy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (!this.hasAttribute('data-title')) return original.call(this)
      const { left: at, right, top, bottom } = box
      return { left: at, right, top, bottom, width: right - at, height: bottom - top, x: at, y: top, toJSON: () => ({}) } as DOMRect
    })
    return () => spy.mockRestore()
  }

  it('holds a wrapped compact title above the sheet with the gap, at the zoom it has', async () => {
    viewport.x = left
    viewport.y = 100
    viewport.zoom = 0.375556
    await drawn(paths.process(doc.id, 'widget'))
    useSheetTop.setState({ sheetTop: 313.5625 })
    // the title wraps over two lines in compact detail, ending 1.5 px under the sheet
    const restore = titled({ left: 100, right: 400, top: 291.047, bottom: 315.083 })
    try {
      act(() => useUi.setState({ sheetOpen: true }))
      await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
      const [view] = moved.mock.calls[0]
      expect(view.zoom).toBe(0.375556)
      expect(view.x).toBe(left)
      expect(view.y).toBeCloseTo(100 + (313.5625 - ISLAND_GAP - 315.083), 4)
    } finally {
      restore()
    }
  })

  it('leaves a compact title the sheet does not reach where it is, whatever the header geometry says', async () => {
    viewport.x = left
    // the geometric header box would sit under the sheet here; the title it draws does not
    viewport.y = 600
    viewport.zoom = 0.375556
    await drawn(paths.process(doc.id, 'widget'))
    useSheetTop.setState({ sheetTop: 313.5625 })
    const restore = titled({ left: 100, right: 400, top: 200, bottom: 224 })
    try {
      act(() => useUi.setState({ sheetOpen: true }))
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(moved).not.toHaveBeenCalled()
    } finally {
      restore()
    }
  })

  it('falls back to the header geometry while the compact title is not measured', async () => {
    viewport.x = left
    viewport.y = 600
    viewport.zoom = 0.375556
    await drawn(paths.process(doc.id, 'widget'))
    act(() => useUi.setState({ sheetOpen: true }))
    await waitFor(() => expect(moved).toHaveBeenCalledTimes(1))
    const headerBottom = viewport.y + (widget.y + CARD.header_height) * viewport.zoom
    const [view] = moved.mock.calls[0]
    expect(view.zoom).toBe(0.375556)
    expect(view.y).toBeCloseTo(viewport.y + (bottom - headerBottom), 4)
  })

  it('pans to no card where the details name none', async () => {
    viewport.x = left
    viewport.y = 100
    await drawn(`/systems/${doc.id}/general`)
    act(() => useUi.setState({ sheetOpen: true }))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(moved).not.toHaveBeenCalled()
  })
})
