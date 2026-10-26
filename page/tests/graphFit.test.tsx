import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import type { LogEntry, ProductSystem } from '@/api/types'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { runCanvas } from '@/window/shortcuts'
import { layoutAnswer } from './placements'
import log from './fixtures/log.json'
import system from './fixtures/system.json'

type Viewport = { x: number; y: number; zoom: number }
type Moves = { onMoveStart?: (event: MouseEvent | null, viewport: Viewport) => void; onNodeDragStart?: () => void }

const fitted = vi.hoisted(() => vi.fn())
const centred = vi.hoisted(() => vi.fn())
const measured = vi.hoisted(() => ({ value: true }))
const flowProps = vi.hoisted(() => ({ current: {} as Moves }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const original = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...original,
    ReactFlow: (props: Record<string, unknown>) => {
      flowProps.current = props as unknown as Moves
      return createElement(original.ReactFlow as never, props as never)
    },
    useReactFlow: () => ({ ...original.useReactFlow(), fitView: fitted, setCenter: centred }),
    useNodesInitialized: () => measured.value,
  }
})

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, layout: vi.fn() } }
})

const doc = system.value as ProductSystem
const VIEW: Viewport = { x: 0, y: 0, zoom: 1 }

function shifted() {
  const answer = layoutAnswer(doc)
  return { ...answer, value: { ...answer.value, cards: answer.value.cards.map((card, at) => (at === 0 ? { ...card, x: card.x + 120 } : card)) } }
}

function entryAt(seq: number, exchangeId: string): LogEntry {
  return { ...(log.value[0] as LogEntry), seq, changes: [{ op: 'add', entity: 'exchange', id: exchangeId, field: null, before: null, after: null }] } as LogEntry
}

const TO_WIDGET = '73b7d6fd-7d08-53d6-bd18-093e6cd44574'

function Graph({ client, product = doc, latest = null }: { client: QueryClient; product?: ProductSystem; latest?: LogEntry | null }) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TooltipProvider>
          <ModelGraph system={product} latest={latest} />
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

beforeEach(() => {
  fitted.mockClear()
  measured.value = true
  vi.mocked(api.layout).mockImplementation(async () => layoutAnswer(doc))
})

it('fits the drawing once its cards are first measured, at no more than full size', async () => {
  measured.value = false
  const client = new QueryClient()
  const view = render(<Graph client={client} />)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(fitted).not.toHaveBeenCalled()
  measured.value = true
  view.rerender(<Graph client={client} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  // the toolbar's height (0 in jsdom) plus a margin stays clear below the cards
  expect(fitted.mock.calls[0][0]).toMatchObject({ maxZoom: 1, padding: { bottom: '24px' } })
})

it('fits again, moving, whenever the arrangement changes while it follows', async () => {
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  await arranged(client)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(2))
  expect(fitted.mock.calls[1][0]).toMatchObject({ duration: 250, maxZoom: 1 })
})

it('stops following on a move the person makes, and follows again from the toolbar', async () => {
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
  act(() => flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW))
  const follow = await screen.findByRole('button', { name: 'Follow the build' })
  await arranged(client)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(fitted).toHaveBeenCalledTimes(1)
  fireEvent.click(follow)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('keeps following through a move the page makes itself', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  act(() => flowProps.current.onMoveStart?.(null, VIEW))
  expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument()
})

it('stops following when the person drags a card', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  act(() => flowProps.current.onNodeDragStart?.())
  expect(await screen.findByRole('button', { name: 'Follow the build' })).toBeInTheDocument()
})

it('stops following when the person zooms with the canvas controls', async () => {
  render(<Graph client={new QueryClient()} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole('button', { name: 'Zoom In' }))
  expect(await screen.findByRole('button', { name: 'Follow the build' })).toBeInTheDocument()
})

it('follows another system the canvas switches to, even when following was paused', async () => {
  const client = new QueryClient()
  const view = render(<Graph client={client} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  act(() => flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW))
  await screen.findByRole('button', { name: 'Follow the build' })
  view.rerender(<Graph client={client} product={{ ...doc, id: 'another' }} />)
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Follow the build' })).not.toBeInTheDocument())
})

it('frames the card a new entry changed, and fits the whole drawing once the build goes quiet', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    const client = new QueryClient()
    const view = render(<Graph client={client} latest={entryAt(1, TO_WIDGET)} />)
    await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
    // the entry already there when the canvas opened is not framed
    expect(fitted.mock.calls[0][0].nodes).toBeUndefined()
    view.rerender(<Graph client={client} latest={entryAt(2, TO_WIDGET)} />)
    // the changed card is framed; whether its supplier joins it depends on the canvas size
    await waitFor(() => expect(fitted.mock.calls.at(-1)?.[0].nodes).toContainEqual({ id: 'widget' }))
    expect(fitted.mock.calls.at(-1)?.[0]).toMatchObject({ duration: 250, maxZoom: 1 })
    const framed = fitted.mock.calls.length
    act(() => vi.advanceTimersByTime(10_000))
    await waitFor(() => expect(fitted.mock.calls.length).toBeGreaterThan(framed))
    expect(fitted.mock.calls.at(-1)?.[0].nodes).toBeUndefined()
  } finally {
    vi.useRealTimers()
  }
})

it('frames nothing while following is paused', async () => {
  const client = new QueryClient()
  const view = render(<Graph client={client} latest={entryAt(1, TO_WIDGET)} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  act(() => flowProps.current.onMoveStart?.(new MouseEvent('mousedown'), VIEW))
  await screen.findByRole('button', { name: 'Follow the build' })
  view.rerender(<Graph client={client} latest={entryAt(2, TO_WIDGET)} />)
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(fitted).toHaveBeenCalledTimes(1)
})

it('centres a process it is asked to show, at the zoom it has, and stops following', async () => {
  centred.mockClear()
  const client = new QueryClient()
  render(<Graph client={client} />)
  await waitFor(() => expect(fitted).toHaveBeenCalledTimes(1))
  act(() => runCanvas({ show: 'widget' }))
  await waitFor(() => expect(centred).toHaveBeenCalledTimes(1))
  const card = layoutAnswer(doc).value.cards.find((c) => c.code === 'widget')!
  const [x, y, options] = centred.mock.calls[0]
  expect(x).toBeCloseTo(card.x + card.width / 2)
  expect(y).toBeCloseTo(card.y + card.height / 2)
  expect(options).toMatchObject({ duration: 250 })
  expect(await screen.findByRole('button', { name: /Follow the build/ })).toBeInTheDocument()
})
