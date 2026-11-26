import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { NodeChange } from '@xyflow/react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Answer, Arrangement, CardGeometry, LogEntry, ProductSystem } from '@/api/types'
import { ApiError, api } from '@/api/client'
import { formatAmount } from '@/lib/format'
import { paths } from '@/lib/paths'
import { layoutAnswer, placementsFor } from './placements'
import type { Outlines, OwnShown } from '@/editors/graph/build'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { useUi } from '@/store/ui'
import { Slot, SlotsProvider } from '@/window/slots'
import system from './fixtures/system.json'
import elementaryFlow from './fixtures/elementary_flow.json'

const flowProps = vi.hoisted(() => ({ onNodesChange: null as unknown as (changes: NodeChange[]) => void }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const original = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...original,
    ReactFlow: (props: Record<string, unknown>) => {
      flowProps.onNodesChange = props.onNodesChange as never
      return createElement(original.ReactFlow as never, props as never)
    },
  }
})

const answered: { release: () => void } = { release: () => undefined }
const flowAnswer = vi.fn(
  () =>
    new Promise((resolve) => {
      answered.release = () => resolve({ ...elementaryFlow, value: { ...elementaryFlow.value, name: 'Carbon dioxide, fossil', flow_type: 'emission', compartment: 'air', sub_compartment: null, side: 'output' } })
    }),
)

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      elementaryFlow: () => flowAnswer(),
      layout: vi.fn(async (_id: string, variant: string | null, expanded: string[] = []) => (variant === null ? null : rendered.layouts[variant]) ?? rendered.layout ?? layoutAnswer(rendered.system as ProductSystem, expanded)),
      placeCards: vi.fn(async () => layoutAnswer(rendered.system as ProductSystem)),
      releaseCards: vi.fn(async () => layoutAnswer(rendered.system as ProductSystem)),
      systemAs: vi.fn(async (_id: string, variant: string) => ({ value: varied(rendered.system as ProductSystem, variant), open_requests: 0, hint: null, view_url: null })),
    },
  }
})

const doc = system.value as ProductSystem

function Address() {
  const location = useLocation()
  return <span data-testid="address">{location.pathname}</span>
}

const address = () => screen.getByTestId('address').textContent ?? ''

function varied(product: ProductSystem, variant: string): ProductSystem {
  // the heavy case doubles the widget's steel in this double of the route
  const factor = variant === 'heavy' ? 2 : 1
  return { ...product, processes: product.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: p.exchanges.map((e) => (e.name === 'steel' ? { ...e, amount: e.amount * factor } : e)) } : p)) }
}

const ROW = 22

const { rendered } = vi.hoisted(() => ({ rendered: { system: null as unknown, layout: null as unknown as Answer<Arrangement> | null, layouts: {} as Record<string, Answer<Arrangement>> } }))


function Graph({ client, product, outlines, latest = null, owns, at = '/' }: { client: QueryClient; product: ProductSystem; outlines?: Outlines; latest?: LogEntry | null; owns?: Map<string, OwnShown>; at?: string }) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <TooltipProvider>
          <SlotsProvider>
            <Slot name="tools" className="slot-tools" />
            <Slot name="view" className="slot-view" />
            <Slot name="minimap" className="slot-minimap" />
            <Slot name="notice" className="slot-notice" />
            <ModelGraph system={product} latest={latest} outlines={outlines} owns={owns} />
            <Address />
          </SlotsProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function renderGraph(product: ProductSystem, outlines?: Outlines, latest: LogEntry | null = null, owns?: Map<string, OwnShown>, at = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  rendered.system = product
  const view = render(<Graph at={at} client={client} product={product} outlines={outlines} latest={latest} owns={owns} />)
  return {
    ...view,
    redraw: (next: ProductSystem) => {
      rendered.system = next
      view.rerender(<Graph client={client} product={next} />)
    },
  }
}

function manyRows(prefix: string, count: number): ProductSystem {
  const widget = doc.processes.find((p) => p.code === 'widget')!
  const input = widget.exchanges.find((e) => e.type !== 'production')!
  const many = Array.from({ length: count }, (_, i) => ({ ...input, id: `many-${i}`, name: `${prefix} ${i + 1}` }))
  return { ...doc, processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges.filter((e) => e.type === 'production'), ...many] } : p)) }
}

function positionOf(container: HTMLElement, id: string): string | null {
  const node = container.querySelector(`.react-flow__node[data-id="${id}"]`) as HTMLElement | null
  return node ? node.style.transform : null
}

function ownPartsOf(): Map<string, OwnShown> {
  return new Map([
    ['widget', { score: 2.49, fraction: 0.5988, unit: 'kg CO2-Eq' }],
    ['frame', { score: 1.668, fraction: 0.4012, unit: 'kg CO2-Eq' }],
  ])
}

function badgeOf(container: HTMLElement, code: string): HTMLElement {
  return container.querySelector(`.react-flow__node[data-id="${code}"] [data-own]`) as HTMLElement
}

function more(): void {
  fireEvent.keyDown(screen.getByRole('button', { name: 'More canvas options' }), { key: 'Enter' })
}

function choose(name: RegExp): void {
  more()
  fireEvent.click(screen.getByRole('menuitemcheckbox', { name }))
}

describe('model graph', () => {
  beforeEach(() => useUi.setState({ canvasSystemId: doc.id, canvasVariant: null }))

  it('draws the reference card from the system, and none while the system has no reference', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const view = renderGraph({ ...doc, reference_process: 'widget' })
    await waitFor(() => expect(view.container.querySelector('[class*="outline-[2.5px]"]')).not.toBeNull())
    expect(within(view.container.querySelector('[class*="outline-[2.5px]"]') as HTMLElement).getByText(widget.name)).toBeInTheDocument()
    view.unmount()
    const unset = renderGraph({ ...doc, reference_process: null })
    await waitFor(() => expect(unset.container.querySelectorAll('.react-flow__node').length).toBeGreaterThan(0))
    expect(unset.container.querySelector('[class*="outline-[2.5px]"]')).toBeNull()
  })

  it('marks the title each card draws, for the canvas to measure where it sits', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const { container } = renderGraph(doc)
    const title = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"] [data-title]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(title.textContent).toBe(widget.name)
  })

  it("opens a background input from its card's row beside the graph, under the system's own address", async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const card = within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    const steel = doc.processes.find((p) => p.code === 'widget')!.exchanges.find((e) => e.name === 'steel')!
    const input = steel.input as { database: string; id: string }
    await waitFor(() => expect(card.getByText('steel').closest('a')?.getAttribute('href')).toBe(`/systems/${doc.id}/datasets/${input.database}/${input.id}`))
  })

  it('folds the inputs of a card past six behind a row of its own, at the card\'s own height', async () => {
    const product = manyRows('input number', 9)
    const { container } = renderGraph(product)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const node = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement
    const card = within(node)
    await waitFor(() => expect(card.getByText('input number 6')).toBeInTheDocument())
    expect(card.queryByText('input number 7')).not.toBeInTheDocument()
    const placement = placementsFor(product).find((p) => p.code === 'widget')!
    expect(card.getByText('Show 3 more inputs').closest('a')).toBeNull()
    expect((node.firstElementChild as HTMLElement).style.height).toBe(`${placement.height}px`)
    const foldAnchor = placement.inputs[placement.shown_inputs]!.y
    const handles = new Map(Array.from(node.querySelectorAll<HTMLElement>('.react-flow__handle.target')).map((h) => [h.dataset.handleid, h.style.top]))
    for (const hidden of ['many-6', 'many-7', 'many-8']) expect(handles.get(hidden)).toBe(`${foldAnchor}px`)
    expect(handles.get('many-5')).toBe(`${foldAnchor - ROW}px`)
  })

  it('opens a card\'s folded rows inside it and folds them again, writing nothing', async () => {
    const product = manyRows('input number', 9)
    vi.mocked(api.placeCards).mockClear()
    vi.mocked(api.layout).mockClear()
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('input number 6')).toBeInTheDocument())
    fireEvent.click(card().getByText('Show 3 more inputs'))
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    expect(vi.mocked(api.layout).mock.calls.map((call) => call[2])).toContainEqual(['widget'])
    expect(api.placeCards).not.toHaveBeenCalled()
    const node = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement
    const expanded = placementsFor(product, ['widget']).find((p) => p.code === 'widget')!
    expect((node.firstElementChild as HTMLElement).style.height).toBe(`${expanded.height}px`)
    expect(card().queryByText(/more inputs/)).not.toBeInTheDocument()
    const handles = Array.from(node.querySelectorAll<HTMLElement>('.react-flow__handle.target')).map((h) => h.style.top)
    expect(new Set(handles).size).toBe(handles.length)
    fireEvent.click(card().getByLabelText('Collapse the rows'))
    await waitFor(() => expect(card().queryByText('input number 7')).not.toBeInTheDocument())
    expect(vi.mocked(api.layout).mock.calls.map((call) => call[2])).toContainEqual([])
  })

  it('opens the details of the card a deliberate click activates, showing a closed inspector again', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    useUi.setState({ inspector: 'closed', sheetOpen: false, chosenProcess: null })
    const { container } = renderGraph(doc)
    const node = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement | null
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    fireEvent.click(node)
    expect(address()).toBe(paths.process(doc.id, widget.code))
    expect(useUi.getState().inspector).toBe('open')
    expect(useUi.getState().chosenProcess).toBe(widget.id)
    useUi.setState({ inspector: 'open', chosenProcess: null })
  })

  it('shows a closed inspector again on a card of the process the address already shows', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    useUi.setState({ inspector: 'closed', sheetOpen: false, chosenProcess: null })
    const { container } = renderGraph(doc, undefined, null, undefined, paths.process(doc.id, widget.code))
    const node = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement | null
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    fireEvent.click(node)
    expect(address()).toBe(paths.process(doc.id, widget.code))
    expect(useUi.getState().inspector).toBe('open')
    useUi.setState({ inspector: 'open' })
  })

  it('keeps a click on a card\'s fold to its own rows, opening no details', async () => {
    const product = manyRows('input number', 9)
    useUi.setState({ inspector: 'closed', sheetOpen: false })
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 3 more inputs')).toBeInTheDocument())
    fireEvent.click(card().getByText('Show 3 more inputs'))
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    expect(address()).toBe('/')
    expect(useUi.getState().inspector).toBe('closed')
    useUi.setState({ inspector: 'open' })
  })

  it('shows a closed inspector again on the title of the card the address already shows', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    useUi.setState({ inspector: 'closed', sheetOpen: false, chosenProcess: null })
    const { container } = renderGraph(doc, undefined, null, undefined, paths.process(doc.id, widget.code))
    const title = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"] a') as HTMLAnchorElement | null
      expect(found).not.toBeNull()
      return found as HTMLAnchorElement
    })
    fireEvent.click(title)
    expect(address()).toBe(paths.process(doc.id, widget.code))
    expect(useUi.getState().inspector).toBe('open')
    useUi.setState({ inspector: 'open' })
  })

  it('shows a closed inspector again on a row\'s link to the page it opens, and leaves it closed on a modified activation', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const steel = widget.exchanges.find((e) => e.name === 'steel')!
    const input = steel.input as { database: string; id: string }
    useUi.setState({ inspector: 'closed', sheetOpen: false })
    const { container } = renderGraph(doc)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('steel').closest('a')).not.toBeNull())
    fireEvent.click(card().getByText('steel'), { ctrlKey: true })
    expect(useUi.getState().inspector).toBe('closed')
    fireEvent.click(card().getByText('steel'))
    expect(address()).toBe(paths.dataset(doc.id, input.database, input.id))
    expect(useUi.getState().inspector).toBe('open')
    useUi.setState({ inspector: 'open' })
  })

  it('shows a closed inspector again on a foreground row\'s link to the process it opens', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const frame = widget.exchanges.find((e) => e.input?.kind === 'foreground')!
    const code = (frame.input as { code: string }).code
    useUi.setState({ inspector: 'closed', sheetOpen: false })
    const { container } = renderGraph(doc)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText(frame.name).closest('a')).not.toBeNull())
    fireEvent.click(card().getByText(frame.name))
    expect(address()).toBe(paths.process(doc.id, code))
    expect(useUi.getState().inspector).toBe('open')
    useUi.setState({ inspector: 'open' })
  })

  it('leaves a docked result on a card click without opening its details, and dismisses the inspector only on a bare graph', async () => {
    useUi.setState({ inspector: 'open', sheetOpen: false, chosenProcess: null })
    const { container } = renderGraph(doc, undefined, null, undefined, `/systems/${doc.id}/results/impact`)
    const node = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement | null
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    fireEvent.click(node)
    expect(address()).toBe(`/systems/${doc.id}`)
    expect(useUi.getState().inspector).toBe('open')
    fireEvent.click(container.querySelector('.react-flow__pane') as HTMLElement)
    expect(useUi.getState().inspector).toBe('closed')
    useUi.setState({ inspector: 'open', chosenProcess: null })
  })

  it('dismisses a shown inspector on a blank click of the canvas, under the system the graph draws', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    useUi.setState({ inspector: 'open', sheetOpen: false, chosenProcess: widget.id })
    const { container } = renderGraph(doc, undefined, null, undefined, paths.system(doc.id))
    await waitFor(() => expect(container.querySelector('.react-flow__pane')).not.toBeNull())
    fireEvent.click(container.querySelector('.react-flow__pane') as HTMLElement)
    expect(useUi.getState().inspector).toBe('closed')
    expect(useUi.getState().chosenProcess).toBeNull()
    useUi.setState({ inspector: 'open' })
  })

  it('keeps a closed inspector closed on a blank click of the canvas', async () => {
    useUi.setState({ inspector: 'closed', sheetOpen: false })
    const { container } = renderGraph(doc, undefined, null, undefined, paths.system(doc.id))
    await waitFor(() => expect(container.querySelector('.react-flow__pane')).not.toBeNull())
    fireEvent.click(container.querySelector('.react-flow__pane') as HTMLElement)
    expect(useUi.getState().inspector).toBe('closed')
  })

  it('dismisses the sheet on a blank click of the canvas below 768 px', async () => {
    const width = window.innerWidth
    window.innerWidth = 700
    useUi.setState({ inspector: 'open', sheetOpen: true })
    const { container } = renderGraph(doc, undefined, null, undefined, paths.system(doc.id))
    await waitFor(() => expect(container.querySelector('.react-flow__pane')).not.toBeNull())
    fireEvent.click(container.querySelector('.react-flow__pane') as HTMLElement)
    expect(useUi.getState().sheetOpen).toBe(false)
    expect(useUi.getState().inspector).toBe('open')
    window.innerWidth = width
    useUi.setState({ sheetOpen: false })
  })

  it('folds the output rows of a card past six, keeping the production output', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const emission = widget.exchanges.find((e) => e.type === 'elementary')!
    // the production row and the emission the fixture already carries, then seven more output rows
    const many = Array.from({ length: 6 }, (_, i) => ({ ...emission, id: `out-${i}`, name: `output number ${i + 1}` }))
    const product: ProductSystem = { ...doc, processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, ...many] } : p)) }
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 2 more outputs')).toBeInTheDocument())
    expect(card().getByText('output number 4')).toBeInTheDocument()
    expect(card().queryByText('output number 5')).not.toBeInTheDocument()
    const placement = placementsFor(product).find((p) => p.code === 'widget')!
    expect(placement.folded_outputs).toBe(2)
  })

  it('places a card it dragged and answers the rows it shows', async () => {
    const product = manyRows('input number', 9)
    vi.mocked(api.placeCards).mockClear()
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 3 more inputs')).toBeInTheDocument())
    fireEvent.click(card().getByText('Show 3 more inputs'))
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    await act(async () => {
      flowProps.onNodesChange([{ type: 'position', id: 'widget', position: { x: 40, y: 60 }, dragging: false }])
    })
    await waitFor(() => expect(api.placeCards).toHaveBeenCalled())
    expect(vi.mocked(api.placeCards).mock.calls[0].slice(1)).toEqual([[{ code: 'widget', x: 40, y: 60 }], null, ['widget']])
  })

  it('asks the layout under the case the canvas shows and the rows it opens', async () => {
    const product = manyRows('input number', 9)
    vi.mocked(api.layout).mockClear()
    const { container, getByLabelText } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 3 more inputs')).toBeInTheDocument())
    fireEvent.click(card().getByText('Show 3 more inputs'))
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    fireEvent.change(getByLabelText('State'), { target: { value: 'heavy' } })
    await waitFor(() => expect(vi.mocked(api.systemAs)).toHaveBeenCalledWith(doc.id, 'heavy'))
    await waitFor(() =>
      expect(vi.mocked(api.layout).mock.calls.map((call) => [call[1], call[2]])).toContainEqual(['heavy', ['widget']]),
    )
  })

  it('resets the layout under the rows the canvas shows', async () => {
    const product = manyRows('input number', 9)
    vi.mocked(api.releaseCards).mockClear()
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 3 more inputs')).toBeInTheDocument())
    fireEvent.click(card().getByText('Show 3 more inputs'))
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    more()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset layout' }))
    await waitFor(() => expect(api.releaseCards).toHaveBeenCalledWith(product.id, null, ['widget']))
  })

  it('expands every card from the canvas options and folds them all again', async () => {
    const product = manyRows('input number', 9)
    vi.mocked(api.layout).mockClear()
    const { container } = renderGraph(product)
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('Show 3 more inputs')).toBeInTheDocument())
    choose(/All rows/)
    await waitFor(() => expect(card().getByText('input number 9')).toBeInTheDocument())
    more()
    expect(screen.getByRole('menuitemcheckbox', { name: /All rows/ })).toHaveAttribute('aria-checked', 'true')
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
    expect(vi.mocked(api.layout).mock.calls.map((call) => call[2])).toContainEqual(['frame', 'widget'])
    choose(/All rows/)
    await waitFor(() => expect(card().queryByText('input number 9')).not.toBeInTheDocument())
    expect(card().getByText('Show 3 more inputs')).toBeInTheDocument()
  })

  it('sizes the card, its header, its section labels and its rows from the geometry the layout hands it', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const sized: CardGeometry = { width: 321, header_height: 44, section_padding: 8, section_label: 20, row_height: 26 }
    const base = layoutAnswer(doc)
    rendered.layout = { ...base, value: { ...base.value, card: sized } }
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const node = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement
    const card = within(node)
    expect((node.firstElementChild as HTMLElement).style.width).toBe('321px')
    expect((card.getByText(widget.name).closest('div') as HTMLElement).style.height).toBe('44px')
    expect(card.getByText('›› Input flows').style.height).toBe('20px')
    expect((node.querySelector('[data-zero]') as HTMLElement).style.height).toBe('26px')
    rendered.layout = null
  })

  it('lists rows in use before rows at zero, mutes the zero ones and names them in the fold', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const input = widget.exchanges.find((e) => e.type !== 'production')!
    const many = Array.from({ length: 9 }, (_, i) => ({ ...input, id: `many-${i}`, name: `input number ${i + 1}`, amount: i < 3 ? 0 : 1, formula: null }))
    const product: ProductSystem = { ...doc, processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges.filter((e) => e.type === 'production'), ...many] } : p)) }
    const { container } = renderGraph(product)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const card = within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    // the six rows with an amount come first; the three at zero fold away
    await waitFor(() => expect(card.getByText('input number 4')).toBeInTheDocument())
    expect(card.queryByText('input number 1')).not.toBeInTheDocument()
    expect(card.getByText('Show 3 more inputs, 3 of them at zero')).toBeInTheDocument()
    expect(card.getByText('input number 4').closest('[data-zero]')?.getAttribute('data-zero')).toBe('false')
  })

  it('mutes a row at zero and lists it after the rows in use', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const input = widget.exchanges.find((e) => e.type !== 'production')!
    const few = Array.from({ length: 3 }, (_, i) => ({ ...input, id: `few-${i}`, name: `input number ${i + 1}`, amount: i === 0 ? 0 : 1, formula: null }))
    const product: ProductSystem = { ...doc, processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges.filter((e) => e.type === 'production'), ...few] } : p)) }
    const { container } = renderGraph(product)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const card = within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card.getByText('input number 1')).toBeInTheDocument())
    const inputs = card.getByText('›› Input flows').parentElement!
    expect(Array.from(inputs.querySelectorAll('[data-zero]')).map((row) => row.getAttribute('data-zero'))).toEqual(['false', 'false', 'true'])
    expect(card.getByText('input number 1').closest('[data-zero]')?.getAttribute('data-zero')).toBe('true')
  })

  it('redraws the canvas under the case the selector picks', async () => {
    const { container, getByLabelText } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const card = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    await waitFor(() => expect(card().getByText('steel').closest('[data-zero]')?.textContent).toContain('0.5'))
    fireEvent.change(getByLabelText('State'), { target: { value: 'heavy' } })
    await waitFor(() => expect(card().getByText('steel').closest('[data-zero]')?.textContent).toContain('1'))
    expect(card().getByText('steel').closest('[data-zero]')?.textContent).not.toContain('0.5')
  })

  it('writes the case the State selector picks to the store', async () => {
    const { getByLabelText } = renderGraph(doc)
    fireEvent.change(getByLabelText('State'), { target: { value: 'heavy' } })
    expect(useUi.getState().canvasVariant).toBe('heavy')
  })

  it('draws the canvas under the state the store holds', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const steel = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement).getByText('steel').closest('[data-zero]') as HTMLElement
    await waitFor(() => expect(steel().textContent).toContain('0.5'))
    act(() => useUi.getState().setCanvasVariant('heavy'))
    await waitFor(() => expect(steel().textContent).toContain('1'))
  })

  it('draws the base values while the state belongs to another system on the canvas', async () => {
    useUi.setState({ canvasSystemId: 'another', canvasVariant: 'heavy' })
    vi.mocked(api.systemAs).mockClear()
    vi.mocked(api.layout).mockClear()
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const steel = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement).getByText('steel').closest('[data-zero]') as HTMLElement
    await waitFor(() => expect(steel().textContent).toContain('0.5'))
    expect(vi.mocked(api.systemAs).mock.calls.map((call) => call[1])).not.toContain('heavy')
    expect(vi.mocked(api.layout).mock.calls.map((call) => call[1])).not.toContain('heavy')
  })

  it('draws the resolved amount of a formula exchange in place of ƒ when asked', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const frameRow = () => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement).getByText('frame').closest('[data-zero]') as HTMLElement
    await waitFor(() => expect(frameRow().textContent).toContain('ƒ'))
    choose(/Formula values/)
    await waitFor(() => expect(frameRow().textContent).toContain('0.25'))
    expect(frameRow().textContent).not.toContain('ƒ')
    choose(/Formula values/)
  })

  it('starts the minimap closed on a narrow window and open on a wide one, and keeps the choice', async () => {
    const width = window.innerWidth
    useUi.setState({ minimapOpen: null })
    window.innerWidth = 800
    const narrow = renderGraph(doc)
    await waitFor(() => expect(narrow.container.querySelector('.react-flow__node')).not.toBeNull())
    expect(narrow.container.querySelector('.react-flow__minimap')).toBeNull()
    choose(/Minimap/)
    await waitFor(() => expect(narrow.container.querySelector('.react-flow__minimap')).not.toBeNull())
    expect(JSON.parse(localStorage.getItem('ecosemantic-page') ?? '{}').state.minimapOpen).toBe(true)
    narrow.unmount()
    useUi.setState({ minimapOpen: null })
    window.innerWidth = 1280
    const wide = renderGraph(doc)
    await waitFor(() => expect(wide.container.querySelector('.react-flow__minimap')).not.toBeNull())
    wide.unmount()
    window.innerWidth = width
  })

  it('draws an explicit empty state carrying the troubles when there is no card', async () => {
    const empty: ProductSystem = { ...doc, processes: [] }
    const view = renderGraph(empty)
    expect(await view.findByText('No card to draw')).toBeInTheDocument()
  })

  it('holds the canvas toolbar in the tools island, wrapping within it', async () => {
    const { container } = renderGraph(doc)
    const toolbar = await waitFor(() => {
      const found = container.querySelector('[role="toolbar"][aria-label="Canvas"]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(toolbar.closest('.react-flow__panel')).toBeNull()
    expect(toolbar.closest('.slot-tools')).not.toBeNull()
    expect(toolbar.className).toContain('max-w-full')
    expect(toolbar.querySelector('[data-wrap]')?.className).toContain('flex-wrap')
  })

  it('draws the minimap in its own slot at its own size, and nothing there while it is off', async () => {
    useUi.setState({ minimapOpen: true })
    const on = renderGraph(doc)
    const minimap = await waitFor(() => {
      const found = on.container.querySelector('.react-flow__minimap') as HTMLElement | null
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(minimap.closest('.slot-minimap')).not.toBeNull()
    expect(minimap.style.position).toBe('static')
    expect(minimap.style.margin).toBe('0px')
    expect(minimap.className).toContain('rounded-md')
    expect(minimap.className).toContain('border')
    expect(minimap.style.getPropertyValue('--xy-minimap-mask-background-color-props')).toBe('rgb(var(--muted) / 0.6)')
    on.unmount()
    useUi.setState({ minimapOpen: false })
    const off = renderGraph(doc)
    await waitFor(() => expect(off.container.querySelector('.react-flow__node')).not.toBeNull())
    expect(off.container.querySelector('.react-flow__minimap')).toBeNull()
    useUi.setState({ minimapOpen: null })
  })

  it('rings the chosen process with a dashed outline set off from the card', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    useUi.setState({ chosenProcess: widget.id })
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"] [data-chosen]')).not.toBeNull())
    expect(container.querySelector('.react-flow__node:not([data-id="widget"]) [data-chosen]')).toBeNull()
    const mark = await waitFor(() => {
      const found = container.querySelector<HTMLElement>('.react-flow__node[data-id="widget"] [data-selection]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(mark.className).toContain('outline-dashed')
    expect(mark.className).toContain('outline-foreground')
    expect(mark.className).toContain('outline-offset-[6px]')
    expect(container.querySelector('.react-flow__node:not([data-id="widget"]) [data-selection]')).toBeNull()
    useUi.setState({ chosenProcess: null })
  })

  it('keeps the highlight ring of a changed card while it is chosen', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const latest: LogEntry = {
      seq: 7,
      timestamp: '2026-11-13T18:37:27.851830Z',
      actor: { kind: 'agent', id: 'fixture-agent', name: 'fixture-agent' },
      source: 'mcp',
      base_hash: null,
      result_hash: 'f91e47f3ae08c28e8c522a058e430636b15174362a6981b055c38026a107c05d',
      changes: [{ op: 'update', entity: 'process', id: widget.id, field: 'name', before: 'a', after: 'b' }],
      message: 'renamed widget',
    }
    useUi.setState({ chosenProcess: widget.id })
    const { container } = renderGraph(doc, undefined, latest)
    const card = await waitFor(() => {
      const found = container.querySelector<HTMLElement>('.react-flow__node[data-id="widget"] [data-chosen]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(card.className).toContain('shadow-[0_0_0_3px_rgb(var(--highlight))]')
    expect(container.querySelector('.react-flow__node[data-id="widget"] [data-selection]')).not.toBeNull()
    useUi.setState({ chosenProcess: null })
  })

  it('keeps the change ring and the selection mark on a chosen card an entry changed', async () => {
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const outlines: Outlines = new Map([['widget', 'rgb(var(--chart-2))']])
    useUi.setState({ chosenProcess: widget.id })
    const { container } = renderGraph(doc, outlines)
    const card = await waitFor(() => {
      const found = container.querySelector<HTMLElement>('.react-flow__node[data-id="widget"] [data-chosen]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(card.style.getPropertyValue('--outline')).toBe('rgb(var(--chart-2))')
    expect(card.className).toContain('shadow-[0_0_0_3px_var(--outline)]')
    expect(container.querySelector('.react-flow__node[data-id="widget"] [data-selection]')).not.toBeNull()
    useUi.setState({ chosenProcess: null })
  })

  it('lists the rows of each section in the order the layout gives them', async () => {
    const { container } = renderGraph(doc)
    const card = await waitFor(() => {
      const found = container.querySelector('.react-flow__node[data-id="widget"]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    const inputs = within(card).getByText('›› Input flows').parentElement!
    const outputs = within(card).getByText('Output flows ››').parentElement!
    await waitFor(() => expect(outputs.textContent).toContain('Carbon dioxide, fossil'))
    expect(inputs.textContent).not.toContain('Carbon dioxide, fossil')
    expect(inputs.textContent).toContain('steel')
  })

  it('sets one target handle per input port at the port\'s y, and the output handle at the card\'s output', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"] .react-flow__handle')).not.toBeNull())
    const placement = placementsFor(doc).find((p) => p.code === 'widget')!
    expect(placement.inputs.length).toBeGreaterThan(0)
    const node = container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement
    const targets = Array.from(node.querySelectorAll<HTMLElement>('.react-flow__handle.target'))
    expect(targets.map((h) => h.dataset.handleid)).toEqual(placement.inputs.map((p) => p.exchange_id))
    expect(targets.map((h) => h.style.top)).toEqual(placement.inputs.map((p) => `${p.y}px`))
    expect((node.querySelector('.react-flow__handle.source') as HTMLElement).style.top).toBe(`${placement.output}px`)
    expect((node.firstElementChild as HTMLElement).style.height).toBe(`${placement.height}px`)
  })

  it("each card's badge carries its own part of the band's result", async () => {
    const { container } = renderGraph(doc, undefined, null, ownPartsOf())
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const widget = badgeOf(container, 'widget')
    const frame = badgeOf(container, 'frame')
    expect(widget.textContent).toBe(`own ${formatAmount(2.49)}`)
    expect(widget.title).toBe('Own part: 2.49 kg CO2-Eq, 59.9 %')
    expect(frame.textContent).toBe(`own ${formatAmount(1.668)}`)
  })

  it("stands a card's own part above the selection outline, gapped from it by the card's background", async () => {
    useUi.setState({ chosenProcess: doc.processes.find((p) => p.code === 'widget')!.id })
    const { container } = renderGraph(doc, undefined, null, ownPartsOf())
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"] [data-own]')).not.toBeNull())
    const badge = badgeOf(container, 'widget')
    expect(container.querySelector('.react-flow__node[data-id="widget"] [data-selection]')).not.toBeNull()
    expect(badge.className.split(' ')).toContain('z-10')
    expect(badge.className.split(' ')).toContain('shadow-[0_0_0_2px_rgb(var(--background))]')
    useUi.setState({ chosenProcess: null })
  })

  it("keeps a card's own part the same size and place whether or not the card is chosen", async () => {
    const widgetId = doc.processes.find((p) => p.code === 'widget')!.id
    const unselected = renderGraph(doc, undefined, null, ownPartsOf())
    await waitFor(() => expect(unselected.container.querySelector('.react-flow__node[data-id="widget"] [data-own]')).not.toBeNull())
    const plain = badgeOf(unselected.container, 'widget')
    const plainBox = { className: plain.className, style: plain.getAttribute('style') }
    unselected.unmount()
    useUi.setState({ chosenProcess: widgetId })
    const selected = renderGraph(doc, undefined, null, ownPartsOf())
    await waitFor(() => expect(selected.container.querySelector('.react-flow__node[data-id="widget"] [data-own]')).not.toBeNull())
    const chosen = badgeOf(selected.container, 'widget')
    expect({ className: chosen.className, style: chosen.getAttribute('style') }).toEqual(plainBox)
    useUi.setState({ chosenProcess: null })
  })

  it('a card shows no part without owns', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    expect(container.querySelectorAll('[data-own]')).toHaveLength(0)
  })

  it('a system without stages draws no box', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    expect(container.querySelectorAll('[data-stage]')).toHaveLength(0)
    expect(container.querySelectorAll('.react-flow__edge-tether')).toHaveLength(0)
  })

  it('draws each card where the layout says', async () => {
    const { container } = renderGraph(doc)
    await waitFor(() => expect(positionOf(container, 'widget')).not.toBeNull())
    const expected = placementsFor(doc)
    for (const placement of expected) {
      expect(positionOf(container, placement.code)?.replace(/\s+/g, '')).toContain(`translate(${placement.x}px,${placement.y}px)`)
    }
  })
  it('shows a drag the store refuses and draws the card where the layout holds it', async () => {
    const message = 'the layout of s changed since it was read; read it again'
    vi.mocked(api.placeCards).mockRejectedValueOnce(new ApiError(409, { error: 'conflict', message, details: {} }))
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow__node[data-id="widget"]')).not.toBeNull())
    const held = placementsFor(doc).find((p) => p.code === 'widget')!
    expect(positionOf(container, 'widget')?.replace(/\s+/g, '')).toContain(`translate(${held.x}px,${held.y}px)`)
    await act(async () => {
      flowProps.onNodesChange([{ type: 'position', id: 'widget', position: { x: 900, y: 900 }, dragging: false }])
    })
    expect(await screen.findByRole('status')).toHaveTextContent(message)
    expect(positionOf(container, 'widget')?.replace(/\s+/g, '')).toContain(`translate(${held.x}px,${held.y}px)`)
  })

  it.each(['light', 'dark'] as const)('draws the graph controls in the %s theme in the xyflow colour mode of that name', async (theme) => {
    useUi.getState().setTheme(theme)
    const { container } = renderGraph(doc)
    await waitFor(() => expect(container.querySelector('.react-flow')).not.toBeNull())
    expect(container.querySelector('.react-flow')?.classList.contains(theme)).toBe(true)
  })

  describe('scaled to one unit', () => {
    const FRAME = '73b7d6fd-7d08-53d6-bd18-093e6cd44574'
    const STEEL = '25a8146b-9de6-53b4-801a-9f63ca97e151'
    const PRODUCTION = '7d4b50c8-08f6-59d1-a7dc-08f2fa6b4542'

    function scaledLayout(scaling: string | null = null): Answer<Arrangement> {
      const base = layoutAnswer(doc)
      const cards = base.value.cards.map((c) =>
        c.code === 'widget' ? { ...c, activity: 4, scaled: { [PRODUCTION]: 4, [STEEL]: 2.5, [FRAME]: 1.25 } } : c,
      )
      const edges = [{ provider: 'frame', consumer: 'widget', exchange_id: FRAME, points: [[0, 0], [10, 0]] as [number, number][], label: { x: 12, y: 34, width: 90, height: 16, per_unit: '0.25 kg per unit', scaled: '1.25 kg', formula: 'ƒ kWh' } }]
      return { ...base, value: { ...base.value, cards, edges, scaling } }
    }

    beforeEach(() => {
      rendered.layout = scaledLayout()
      useUi.setState({ scaledView: true, formulaValues: false })
    })
    afterEach(() => {
      rendered.layout = null
    })

    const widget = (container: HTMLElement) => within(container.querySelector('.react-flow__node[data-id="widget"]') as HTMLElement)
    const rowOf = (container: HTMLElement, name: string) => widget(container).getByText(name).closest('[data-zero]') as HTMLElement

    it('reads Scaled to 1 unit and is on by default', async () => {
      renderGraph(doc)
      await waitFor(() => expect(screen.getByRole('button', { name: 'More canvas options' })).toBeInTheDocument())
      more()
      expect(screen.getByRole('menuitemcheckbox', { name: /Scaled to 1 unit/ })).toHaveAttribute('aria-checked', 'true')
    })

    it('shows the scaled amounts in the rows, and the base amounts once off', async () => {
      const { container } = renderGraph(doc)
      await waitFor(() => expect(rowOf(container, 'steel').textContent).toContain(formatAmount(2.5)))
      expect(rowOf(container, 'frame').textContent).toContain(formatAmount(1.25))
      expect(rowOf(container, 'widget').textContent).toContain(formatAmount(4))
      expect(rowOf(container, 'steel').textContent).toContain('kilogram')
      choose(/Scaled to 1 unit/)
      await waitFor(() => expect(rowOf(container, 'steel').textContent).toContain('0.5'))
      expect(rowOf(container, 'steel').textContent).not.toContain('2.5')
      expect(rowOf(container, 'frame').textContent).toContain('ƒ')
    })

    it('marks a row the scaled map lacks with a question mark, never with the per-unit amount', async () => {
      const base = scaledLayout()
      base.value.cards = base.value.cards.map((c) => (c.code === 'widget' ? { ...c, scaled: { [PRODUCTION]: 4, [FRAME]: 1.25 } } : c))
      rendered.layout = base
      const { container } = renderGraph(doc)
      await waitFor(() => expect(rowOf(container, 'steel').textContent).toContain('?'))
      expect(rowOf(container, 'steel').textContent).not.toContain('0.5')
      expect(within(rowOf(container, 'steel')).getByTitle('No scaled amount for this row')).toBeInTheDocument()
      expect(rowOf(container, 'frame').textContent).toContain(formatAmount(1.25))
    })

    it('disables the switch and shows the reason while the layout withholds the scaled view', async () => {
      rendered.layout = scaledLayout('the system has no reference process')
      renderGraph(doc)
      expect(await screen.findByRole('status')).toHaveTextContent('the system has no reference process')
      more()
      expect(screen.getByRole('menuitemcheckbox', { name: /Scaled to 1 unit/ })).toHaveAttribute('aria-disabled', 'true')
    })

    it('asks the layout under the case the selector picks and keeps the switch, scaling under it', async () => {
      const heavy = scaledLayout()
      heavy.value.cards = heavy.value.cards.map((c) => (c.code === 'widget' ? { ...c, scaled: { [PRODUCTION]: 4, [STEEL]: 5, [FRAME]: 1.25 } } : c))
      rendered.layouts = { heavy }
      const { container, getByLabelText } = renderGraph(doc)
      await waitFor(() => expect(rowOf(container, 'steel').textContent).toContain(formatAmount(2.5)))
      fireEvent.change(getByLabelText('State'), { target: { value: 'heavy' } })
      await waitFor(() => expect(rowOf(container, 'steel').textContent).toContain(formatAmount(5)))
      expect(api.layout).toHaveBeenCalledWith(doc.id, 'heavy', [], expect.any(AbortSignal))
      more()
      expect(screen.getByRole('menuitemcheckbox', { name: /Scaled to 1 unit/ })).toHaveAttribute('aria-checked', 'true')
      expect(screen.getByRole('menuitemcheckbox', { name: /Scaled to 1 unit/ })).not.toHaveAttribute('aria-disabled', 'true')
      rendered.layouts = {}
    })

    it('marks a scaled row whose exchange has a formula with ƒ before its number, and the number alone with Formula values on', async () => {
      const { container } = renderGraph(doc)
      await waitFor(() => expect(rowOf(container, 'frame').textContent).toContain(`ƒ ${formatAmount(1.25)}`))
      expect(rowOf(container, 'steel').textContent).not.toContain('ƒ')
      choose(/Formula values/)
      await waitFor(() => expect(rowOf(container, 'frame').textContent).not.toContain('ƒ'))
      expect(rowOf(container, 'frame').textContent).toContain(formatAmount(1.25))
      choose(/Formula values/)
    })
  })
})
