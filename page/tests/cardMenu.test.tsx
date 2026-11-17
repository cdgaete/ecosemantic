import { ReactFlow, ReactFlowProvider, type Node } from '@xyflow/react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useMemo } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import type { Process, ProductSystem } from '@/api/types'
import { LinkedMenuItems, ProcessMenuItems } from '@/editors/graph/CardMenu'
import { clearArea, toolbarFor, TOOLBAR_OFFSET } from '@/editors/graph/layout'
import { ProcessNode } from '@/editors/graph/ProcessNode'
import type { ProcessNodeData } from '@/editors/graph/build'
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

  it('filters the log to the process and shows Activity', () => {
    renderAt(
      '/',
      <>
        <ProcessMenuItems systemId={doc.id} process={process} />
        <Here />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Filter the log to this process' }))
    expect(useUi.getState().chosenProcess).toBe(process.id)
    expect(useUi.getState().inspector).toBe('open')
    expect(screen.getByTestId('here').textContent).toBe(paths.system(doc.id))
    expect(useRequestDialog.getState().target).toBeNull()
  })

  it('centres the card', () => {
    const received = onCanvas()
    renderAt('/', <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('button', { name: 'Focus' }))
    expect(received).toEqual([{ show: process.code }])
  })

  it('asks for a change to the process', () => {
    renderAt('/', <ProcessMenuItems systemId={doc.id} process={process} />)
    fireEvent.click(screen.getByRole('button', { name: 'Request a change' }))
    expect(useRequestDialog.getState().target).toEqual({ systemId: doc.id, entity: 'process', entityId: process.id })
  })

  it('opens and centres a linked system', () => {
    const received = onCanvas()
    renderAt('/', <LinkedMenuItems to={target} node={node} />)
    expect(screen.getByRole('link', { name: 'Open' }).getAttribute('href')).toBe(target)
    fireEvent.click(screen.getByRole('button', { name: 'Focus' }))
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

function Canvas({ at, selected = true }: { at: { x: number; y: number }; selected?: boolean }) {
  const nodes = useMemo<Node<ProcessNodeData, 'process'>[]>(
    () => [
      {
        id: process.code,
        type: 'process',
        position: at,
        selected,
        measured: CARD_SIZE,
        data: { process, reference: false, hot: false, hotExchanges: [], outline: null, systemId: PRODUCT.id, placement: PLACEMENT, card: GEOMETRY },
      },
    ],
    [at, selected],
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
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shifts the selected card\'s toolbar into the clear area the store and the canvas size give it', async () => {
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

  it('places the toolbar of a card selected after the canvas drew it', async () => {
    measuringRow()
    const view = render(<Canvas at={AT} selected={false} />)
    expect(screen.queryByRole('toolbar', { name: 'Card' })).not.toBeInTheDocument()
    view.rerender(<Canvas at={AT} selected />)
    const bar = await screen.findByRole('toolbar', { name: 'Card' })
    const placed = placedFor(AT, CLEARANCE, NATURAL.height)
    expect(bar.style.width).toBe('')
    expect(bar.parentElement?.style.translate).toBe(`${placed.left - AT.x}px 0px`)
  })
})
