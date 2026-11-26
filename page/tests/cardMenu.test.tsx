import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactFlow, ReactFlowProvider, type Node } from '@xyflow/react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useMemo } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import type { Process, ProductSystem } from '@/api/types'
import { LinkedMenuItems, ProcessMenuItems } from '@/editors/graph/CardMenu'
import { clearArea, POINTER_WIDTH, toolbarFor, TOOLBAR_OFFSET } from '@/editors/graph/layout'
import { LinkedNode } from '@/editors/graph/LinkedNode'
import { ProcessNode } from '@/editors/graph/ProcessNode'
import type { LinkedNodeData, ProcessNodeData } from '@/editors/graph/build'
import { paths } from '@/lib/paths'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useClearance } from '@/window/clearance'
import { CANVAS_EVENT, type CanvasCommand } from '@/window/shortcuts'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import { layoutAnswer, placementsFor } from './placements'
import { renderAt } from './render'

const canvasSize = vi.hoisted(() => ({ width: 1024, height: 768 }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const original = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...original,
    useStore: (selector: (state: Record<string, unknown>) => unknown) =>
      original.useStore((state) => selector({ ...(state as unknown as Record<string, unknown>), width: canvasSize.width, height: canvasSize.height })),
  }
})

const doc = system.value as { id: string; processes: Process[] }
const process = doc.processes.find((p) => p.code === 'widget')!
const part = (systems.value as { id: string; name: string }[]).find((s) => s.id !== doc.id)!
const node = `system:${part.id}`
const target = paths.version(part.id, 'ab'.repeat(32))

function onCanvas(): CanvasCommand[] {
  const received: CanvasCommand[] = []
  window.addEventListener(CANVAS_EVENT, (event) => received.push((event as CustomEvent<CanvasCommand>).detail))
  return received
}

function Here() {
  return <span data-testid="here">{useLocation().pathname}</span>
}

describe("a card's menu", () => {
  beforeEach(() => {
    useUi.setState({ inspector: 'closed', sheetOpen: false, chosenProcess: null })
    useRequestDialog.setState({ target: null })
  })

  afterEach(() => {
    useRequestDialog.setState({ target: null })
  })

  it("opens the process's details", () => {
    renderAt('/', <ProcessMenuItems systemId={doc.id} process={process} />)
    const link = screen.getByRole('link', { name: 'Open details' })
    expect(link.getAttribute('href')).toContain(paths.process(doc.id, process.code))
    expect(link.getAttribute('href')?.endsWith(`/processes/${process.code}/general`)).toBe(true)
  })

  it('shows the inspector again on a plain activation of the details link, at the address it already shows', () => {
    renderAt(paths.process(doc.id, process.code), <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('link', { name: 'Open details' }))
    expect(useUi.getState().inspector).toBe('open')
  })

  it.each([
    { ctrlKey: true },
    { metaKey: true },
    { shiftKey: true },
    { altKey: true },
    { button: 1 },
  ])('leaves a closed inspector closed on a modified or non-primary activation: %o', (modifiers) => {
    renderAt(paths.process(doc.id, process.code), <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('link', { name: 'Open details' }), modifiers)
    expect(useUi.getState().inspector).toBe('closed')
  })

  it("offers no details of the process the inspector already shows", () => {
    useUi.setState({ inspector: 'open' })
    renderAt(paths.process(doc.id, process.code), <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.queryByRole('link', { name: 'Open details' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show process activity' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Center card' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request a change' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Filter the log to this process' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Focus' })).not.toBeInTheDocument()
  })

  it.each(['general', 'io'])('offers no details of that process on its %s subtab while the inspector shows it', (page) => {
    useUi.setState({ inspector: 'open' })
    renderAt(paths.process(doc.id, process.code, page), <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.queryByRole('link', { name: 'Open details' })).not.toBeInTheDocument()
  })

  it('offers the details of a process while the inspector shows another one', () => {
    const other = doc.processes.find((p) => p.code !== process.code)!
    useUi.setState({ inspector: 'open', chosenProcess: other.id })
    renderAt(paths.process(doc.id, other.code), <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.getByRole('link', { name: 'Open details' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show process activity' })).toBeInTheDocument()
  })

  it('keeps the subtab the details link of a closed inspector points at', () => {
    const io = paths.process(doc.id, process.code, 'io')
    renderAt(io, <><ProcessMenuItems systemId={doc.id} process={process} /><Here /></>)
    const link = screen.getByRole('link', { name: 'Open details' })
    expect(link.getAttribute('href')?.endsWith(`/processes/${process.code}/io`)).toBe(true)
    fireEvent.click(link)
    expect(useUi.getState().inspector).toBe('open')
    expect(screen.getByTestId('here').textContent).toBe(io)
  })

  it('offers no activity action while the log it filters is the one shown', () => {
    useUi.setState({ inspector: 'open', chosenProcess: process.id })
    renderAt(paths.system(doc.id), <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.queryByRole('button', { name: 'Show process activity' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open details' })).toBeInTheDocument()
  })

  it('offers the activity action while the log filters another process', () => {
    useUi.setState({ inspector: 'open', chosenProcess: null })
    renderAt(paths.system(doc.id), <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.getByRole('button', { name: 'Show process activity' })).toBeInTheDocument()
  })

  it.each([paths.process(doc.id, process.code), paths.system(doc.id)])('offers every action while the inspector is closed at %s', (path) => {
    useUi.setState({ inspector: 'closed', chosenProcess: process.id })
    renderAt(path, <ProcessMenuItems systemId={doc.id} process={process} />)
    expect(screen.getByRole('link', { name: 'Open details' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show process activity' })).toBeInTheDocument()
  })

  it('filters the log to the process and shows Activity', () => {
    renderAt(
      '/',
      <>
        <ProcessMenuItems systemId={doc.id} process={process} />
        <Here />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Show process activity' }))
    expect(useUi.getState().chosenProcess).toBe(process.id)
    expect(useUi.getState().inspector).toBe('open')
    expect(screen.getByTestId('here').textContent).toBe(paths.system(doc.id))
    expect(useRequestDialog.getState().target).toBeNull()
  })

  it('centers the card', () => {
    const received = onCanvas()
    renderAt('/', <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('button', { name: 'Center card' }))
    expect(received).toEqual([{ show: process.code }])
  })

  it('asks for a change to the process', () => {
    renderAt('/', <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('button', { name: 'Request a change' }))
    expect(useRequestDialog.getState().target).toEqual({ systemId: doc.id, entity: 'process', entityId: process.id })
  })

  it('opens and centers a linked system', () => {
    const received = onCanvas()
    renderAt('/', <LinkedMenuItems to={target} node={node} />)
    expect(screen.getByRole('link', { name: 'Open' }).getAttribute('href')).toBe(target)
    fireEvent.click(screen.getByRole('button', { name: 'Center card' }))
    expect(received).toEqual([{ show: node }])
  })
})

const CLEARANCE = { top: 122, right: 384, bottom: 132, left: 68 }
const AT = { x: 412, y: 300 }
const NATURAL = { width: 425, height: 34 }
const WRAPPED_HEIGHT = 102
const PRODUCT = system.value as ProductSystem
const GEOMETRY = layoutAnswer(PRODUCT).value.card
const PLACEMENT = placementsFor(PRODUCT).find((p) => p.code === process.code)!
const CARD_SIZE = { width: GEOMETRY.width, height: PLACEMENT.height }
const NODE_TYPES = { process: ProcessNode }
const ROWS = { expanded: false, toggle: () => undefined }

const OTHER = PRODUCT.processes.find((p) => p.code !== process.code)!
const OTHER_PLACEMENT = placementsFor(PRODUCT).find((p) => p.code === OTHER.code)!
const OTHER_AT = { x: 40, y: 420 }

function Canvas({ at, clicked = null }: { at: { x: number; y: number }; clicked?: string | null }) {
  const nodes = useMemo<Node<ProcessNodeData, 'process'>[]>(
    () => [
      {
        id: process.code,
        type: 'process',
        position: at,
        selected: clicked === process.code,
        measured: CARD_SIZE,
        data: { process, reference: false, hot: false, hotExchanges: [], outline: null, systemId: PRODUCT.id, placement: PLACEMENT, card: GEOMETRY, own: null, supplies: null, rows: ROWS },
      },
      {
        id: OTHER.code,
        type: 'process',
        position: OTHER_AT,
        selected: clicked === OTHER.code,
        measured: { width: GEOMETRY.width, height: OTHER_PLACEMENT.height },
        data: { process: OTHER, reference: false, hot: false, hotExchanges: [], outline: null, systemId: PRODUCT.id, placement: OTHER_PLACEMENT, card: GEOMETRY, own: null, supplies: null, rows: ROWS },
      },
    ],
    [at, clicked],
  )
  return (
    <MemoryRouter>
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} nodeTypes={NODE_TYPES} proOptions={{ hideAttribution: true }} />
      </ReactFlowProvider>
    </MemoryRouter>
  )
}

function measuringRow(): void {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const bar = this.getAttribute('aria-label') === 'Card'
    const given = bar ? Number.parseFloat((this as HTMLElement).style.width) : Number.NaN
    const wrapped = bar && given < NATURAL.width
    const width = bar ? (wrapped ? given : NATURAL.width) : 0
    const height = bar ? (wrapped ? WRAPPED_HEIGHT : NATURAL.height) : 0
    return { x: 0, y: 0, left: 0, top: 0, right: width, bottom: height, width, height, toJSON: () => ({}) } as DOMRect
  })
}

function placedFor(at: { x: number; y: number }, clearance: typeof CLEARANCE, height: number) {
  return toolbarFor({ card: { ...at, ...CARD_SIZE }, natural: NATURAL, height, clear: clearArea(canvasSize, clearance) })
}

describe("the card toolbar's place on the canvas", () => {
  beforeEach(() => {
    canvasSize.width = 1024
    canvasSize.height = 768
    useClearance.setState({ clearance: CLEARANCE })
    useUi.setState({ chosenProcess: process.id })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shifts the chosen card\'s toolbar into the clear area the store and the canvas size give it', async () => {
    measuringRow()
    render(<Canvas at={AT} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(AT, CLEARANCE, NATURAL.height)
    expect(placed.side).toBe('top')
    expect(placed.width).toBeNull()
    expect(bar.style.width).toBe('')
    expect(bar.parentElement?.style.translate).toBe(`${placed.left - AT.x}px 0px`)
    expect(bar.parentElement?.style.transform).toBe(`translate(${AT.x}px, ${AT.y - TOOLBAR_OFFSET}px) translate(0%, -100%)`)
  })

  it('narrows the toolbar to the clear area and wraps its items when the row does not fit', async () => {
    measuringRow()
    render(<Canvas at={AT} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    expect(bar.style.width).toBe('')
    const narrower = { ...CLEARANCE, right: 700 }
    act(() => useClearance.getState().setClearance(narrower))
    const placed = placedFor(AT, narrower, WRAPPED_HEIGHT)
    expect(placed.width).toBe(256)
    await waitFor(() => expect(bar.style.width).toBe('256px'))
    expect(bar.className).toContain('flex-wrap')
    expect(bar.parentElement?.style.translate).toBe(`${placed.left - AT.x}px 0px`)
  })

  it('puts the toolbar below a card under the top island', async () => {
    measuringRow()
    const below = { x: AT.x, y: 130 }
    render(<Canvas at={below} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(below, CLEARANCE, NATURAL.height)
    expect(placed.side).toBe('bottom')
    expect(bar.parentElement?.style.transform).toBe(`translate(${below.x}px, ${below.y + CARD_SIZE.height + TOOLBAR_OFFSET}px) translate(0%, 0%)`)
  })

  it('puts the toolbar below a card whose wrapped row is too tall for the room above it', async () => {
    measuringRow()
    const narrower = { ...CLEARANCE, right: 700 }
    useClearance.setState({ clearance: narrower })
    // two estimated rows of 34 clear the top at this height; the 102 px the row takes does not
    const tight = { x: AT.x, y: 210 }
    render(<Canvas at={tight} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(tight, narrower, WRAPPED_HEIGHT)
    expect(placed.width).toBe(256)
    expect(placed.side).toBe('bottom')
    await waitFor(() => expect(bar.style.width).toBe('256px'))
    await waitFor(() => expect(bar.parentElement?.style.transform).toBe(`translate(${tight.x}px, ${tight.y + CARD_SIZE.height + TOOLBAR_OFFSET}px) translate(0%, 0%)`))
  })

  it('points its menu at the card it belongs to', async () => {
    measuringRow()
    render(<Canvas at={AT} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(AT, CLEARANCE, NATURAL.height)
    const pointer = bar.querySelector('[data-pointer]')
    expect(pointer?.getAttribute('data-pointer')).toBe('top')
    expect((pointer as HTMLElement).style.left).toBe(`${placed.pointer - POINTER_WIDTH / 2}px`)
  })

  it('points up at the card from a menu under it', async () => {
    measuringRow()
    const below = { x: AT.x, y: 130 }
    render(<Canvas at={below} />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(below, CLEARANCE, NATURAL.height)
    expect(placed.side).toBe('bottom')
    expect(bar.querySelector('[data-pointer]')?.getAttribute('data-pointer')).toBe('bottom')
  })

  it('places the toolbar of a card chosen after the canvas drew it', async () => {
    measuringRow()
    useUi.setState({ chosenProcess: null })
    render(<Canvas at={AT} />)
    expect(screen.queryByRole('toolbar', { name: 'Card' })).not.toBeInTheDocument()
    act(() => useUi.getState().chooseProcess(process.id))
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(AT, CLEARANCE, NATURAL.height)
    expect(bar.style.width).toBe('')
    expect(bar.parentElement?.style.translate).toBe(`${placed.left - AT.x}px 0px`)
  })

  it('draws the toolbar on the chosen card, not on the card whose click chose another', async () => {
    measuringRow()
    useUi.setState({ chosenProcess: OTHER.id })
    render(<Canvas at={AT} clicked={process.code} />)
    const bars = await screen.findAllByRole('toolbar', { name: 'Card' })
    expect(bars).toHaveLength(1)
    expect(bars[0].parentElement?.style.transform).toContain(`translate(${OTHER_AT.x}px,`)
    act(() => useUi.getState().chooseProcess(process.id))
    await waitFor(() => expect(screen.getByRole('toolbar', { name: 'Card' }).parentElement?.style.transform).toContain(`translate(${AT.x}px,`))
    expect(screen.getAllByRole('toolbar', { name: 'Card' })).toHaveLength(1)
  })

  it('draws no toolbar while no process is chosen, whatever card a click selected', () => {
    useUi.setState({ chosenProcess: null })
    render(<Canvas at={AT} clicked={process.code} />)
    expect(screen.queryByRole('toolbar', { name: 'Card' })).not.toBeInTheDocument()
  })

  it('draws the menu of a linked system a click selected, and none while a process is chosen', async () => {
    measuringRow()
    useUi.setState({ chosenProcess: null })
    const linked: Node<LinkedNodeData, 'linked'> = {
      id: node,
      type: 'linked',
      position: AT,
      selected: true,
      measured: CARD_SIZE,
      data: { productSystemId: part.id, atHash: null, case: null, placement: PLACEMENT, card: GEOMETRY },
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <ReactFlowProvider>
            <ReactFlow nodes={[linked]} nodeTypes={{ linked: LinkedNode }} proOptions={{ hideAttribution: true }} />
          </ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('toolbar', { name: 'Card' })).toBeInTheDocument()
    act(() => useUi.getState().chooseProcess(process.id))
    await waitFor(() => expect(screen.queryByRole('toolbar', { name: 'Card' })).not.toBeInTheDocument())
  })
})
