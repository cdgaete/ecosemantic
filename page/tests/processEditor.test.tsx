import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useUi } from '@/store/ui'
import { CANVAS_EVENT } from '@/window/shortcuts'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import { App } from '@/App'
import { ApiError, api } from '@/api/client'
import type { Answer, Arrangement, ElementaryFlow, Exchange, Process, ProductSystem, SystemRead } from '@/api/types'
import { DatasetPeek } from '@/editors/explorer/DatasetPeek'
import { InputsOutputsPage } from '@/editors/process/InputsOutputsPage'
import { ProcessEditor } from '@/editors/process/ProcessEditor'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import elementaryFlows from './fixtures/elementary_flows.json'
import backgroundProcess from './fixtures/background_process.json'

const doc = system.value as ProductSystem
const widget = doc.processes.find((p) => p.code === 'widget')!
const co2 = widget.exchanges.find((e) => e.type === 'elementary')!
const steel = widget.exchanges.find((e) => e.type === 'product' && e.input?.kind === 'background' && e.name === 'steel')!
const flows = elementaryFlows as Answer<ElementaryFlow[]>
const river = flows.value.find((flow) => flow.name === 'Water, river')!
const fossil = flows.value.find((flow) => flow.name === 'Carbon dioxide, fossil')!

const drawn = vi.hoisted(() => ({ system: null as unknown as ProductSystem, held: null as Promise<Answer<Arrangement>> | null, failure: null as Error | null, variant: null as unknown as ProductSystem | null, variantFailure: null as Error | null }))

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      layout: vi.fn((): Promise<Answer<Arrangement>> => {
        if (drawn.failure !== null) return Promise.reject(drawn.failure)
        if (drawn.held !== null) return drawn.held
        return Promise.resolve(layoutAnswer(drawn.system))
      }),
      elementaryFlows: vi.fn(async (_database: string, ids: string[]) => ({
        ...elementaryFlow,
        value: ids.map((id) => ({ ...elementaryFlow.value, ref: { ...elementaryFlow.value.ref, id }, name: co2.name, side: 'output', flow_type: 'inventory indicator' })),
      })),
      elementaryFlow: vi.fn(),
      systemAs: vi.fn(async (_id: string, variant: string) => {
        if (drawn.variantFailure !== null) throw drawn.variantFailure
        return { ...(system as unknown as SystemRead), value: drawn.variant ?? doc, open_requests: 0, hint: null, view_url: null, variant }
      }),
      backgroundProcess: vi.fn(async () => backgroundProcess),
    },
  }
})

beforeEach(() => {
  drawn.system = doc
  drawn.held = null
  drawn.failure = null
  drawn.variant = null
  drawn.variantFailure = null
  useUi.setState({ canvasSystemId: null, canvasVariant: null, chosenEntry: null, chosenProcess: null })
  vi.mocked(api.elementaryFlows).mockClear()
  vi.mocked(api.systemAs).mockClear()
})

const withFrameAmount = (product: ProductSystem, amount: number): ProductSystem => ({
  ...product,
  processes: product.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: p.exchanges.map((e) => (e.name === 'frame' ? { ...e, amount, formula: null } : e)) } : p)),
})

function renderProcess() {
  return renderAt(
    `/systems/${doc.id}/processes/widget/io`,
    <Routes>
      <Route path="/systems/:id/processes/:code/*" element={<ProcessEditor />} />
    </Routes>,
  )
}

function renderRows(product: ProductSystem = doc, process: Process = widget) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/systems/${product.id}/processes/${process.code}/io`]}>
        <TooltipProvider>
          <InputsOutputsPage systemId={product.id} system={product} process={process} state={null} />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function HistoryBack() {
  const navigate = useNavigate()
  return <button onClick={() => navigate(-1)}>history back</button>
}

function renderSuppliers() {
  return renderAt(
    `/systems/${doc.id}/processes/widget/io`,
    <>
      <Routes>
        <Route path="/systems/:id/processes/:code/*" element={<ProcessEditor />} />
        <Route path="/systems/:id/datasets/:database/*" element={<DatasetPeek />} />
      </Routes>
      <HistoryBack />
    </>,
  )
}

const sectionOf = (title: string) => screen.getByText(title).closest('section') as HTMLElement
const rowsOf = (title: string) => Array.from(sectionOf(title).querySelectorAll('tbody tr')).map((row) => row.textContent ?? '')

it('names the flow type and compartment of an elementary flow once the flow is answered', async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  await screen.findByText('Outputs')
  const outputs = sectionOf('Outputs')
  await waitFor(() => expect(outputs.textContent).toContain('inventory indicator · natural resource'))
  expect(outputs.textContent).toContain(co2.name)
  expect(outputs.textContent).toContain(widget.reference_product)
})

it('lists the rows of each section in the order its placement gives', async () => {
  const base = layoutAnswer(doc)
  const cards = base.value.cards.map((card) => (card.code === 'widget' ? { ...card, inputs: [...card.inputs].reverse(), outputs: [...card.outputs].reverse() } : card))
  drawn.held = Promise.resolve({ ...base, value: { ...base.value, cards } })
  const widgetCard = cards.find((card) => card.code === 'widget')!
  const named = (id: string) => widget.exchanges.find((e) => e.id === id)!.name
  renderRows()
  await screen.findByText('Inputs')
  const inputs = await waitFor(() => {
    expect(rowsOf('Inputs').length).toBeGreaterThan(1)
    return rowsOf('Inputs')
  })
  expect(inputs[0]).toContain(named(widgetCard.inputs[0].exchange_id))
  expect(inputs[inputs.length - 1]).toContain(named(widgetCard.inputs[widgetCard.inputs.length - 1].exchange_id))
  const outputs = rowsOf('Outputs')
  expect(outputs[0]).toContain(co2.name)
  expect(outputs[1]).toContain(widget.reference_product)
})

it('reads each exchange’s distribution in the unit its amount is in, and none where it has none', async () => {
  renderRows()
  await screen.findByText('Inputs')
  const inputs = sectionOf('Inputs')
  const steelRow = (await within(inputs).findByText(steel.name)).closest('tr')!
  expect(within(steelRow).getByText('lognormal, GSD² 1.22')).toBeInTheDocument()
  const frame = widget.exchanges.find((e) => e.input?.kind === 'foreground')!
  const frameRow = (await within(inputs).findByText(frame.name)).closest('tr')!
  expect(within(frameRow).getByText('none')).toBeInTheDocument()
})

it('says so while the arrangement of the system loads', async () => {
  drawn.held = new Promise(() => undefined)
  renderRows()
  expect(await screen.findByRole('status')).toHaveTextContent(/where the arrangement places the rows/)
  expect(screen.queryByText('Inputs')).not.toBeInTheDocument()
})

it("shows the arrangement's error in place of the rows", async () => {
  drawn.failure = new ApiError(400, { error: 'invalid', message: 'the arrangement of this system cannot be read', details: {} })
  renderRows()
  expect(await screen.findByText('the arrangement of this system cannot be read')).toBeInTheDocument()
  expect(screen.queryByText('Inputs')).not.toBeInTheDocument()
})

it("shows a background input's provider as the background process's name and location", async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  await screen.findByText('Inputs')
  const inputs = sectionOf('Inputs')
  await waitFor(() => expect(inputs.textContent).toContain(`${backgroundProcess.value.name} · ${backgroundProcess.value.location}`))
  expect(inputs.textContent).toContain(steel.name)
})

it("opens a background input's provider beside the graph, under the system's own address", async () => {
  renderRows()
  await screen.findByText('Inputs')
  const inputs = sectionOf('Inputs')
  const provider = await within(inputs).findAllByRole('link', { name: new RegExp(backgroundProcess.value.name) })
  const input = steel.input as { database: string; id: string }
  expect(provider[0]).toHaveAttribute('href', `/systems/${doc.id}/datasets/${input.database}/${input.id}`)
})

it('shows a linked input as the system it links, linking to that system', async () => {
  const link = { ...steel, id: 'link-exchange', name: 'frame kit', input: { kind: 'system' as const, product_system_id: 'frame-system', at_hash: 'a'.repeat(64), case: null } }
  const linking = { ...doc, id: 'linking-system', processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, link] } : p)) }
  drawn.system = linking
  vi.mocked(api.system).mockImplementation(async (id) => (id === linking.id ? { ...(system as SystemRead), value: linking } : (system as SystemRead)))
  renderAt(`/systems/${linking.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  await screen.findByText('Inputs')
  const inputs = sectionOf('Inputs')
  expect(within(inputs).getByRole('link', { name: 'frame kit · linked system' })).toHaveAttribute('href', '/systems/frame-system')
})

it('reads the elementary flows of a process in one request, showing each row its own flow and naming one the answer lacks', async () => {
  const water: Exchange = { ...co2, id: 'water-exchange', name: river.name, input: { database: river.ref.database, id: river.ref.id, kind: 'elementary_flow' } }
  const missing: Exchange = { ...co2, id: 'missing-exchange', name: 'Ammonia', input: { database: river.ref.database, id: 'no-such-flow', kind: 'elementary_flow' } }
  const withFlows = { ...widget, exchanges: [...widget.exchanges, water, missing] }
  const product = { ...doc, processes: doc.processes.map((p) => (p.code === widget.code ? withFlows : p)) }
  drawn.system = product
  vi.mocked(api.elementaryFlows).mockImplementationOnce(async (_database, ids) => ({
    ...flows,
    value: [fossil, river].filter((flow) => ids.includes(flow.ref.id)),
  }))
  renderRows(product, withFlows)
  await screen.findByText('Outputs')
  const outputs = sectionOf('Outputs')
  const carbon = within(outputs).getByText(fossil.name).closest('tr')!
  await waitFor(() => expect(carbon.textContent).toContain(`${fossil.flow_type} · ${fossil.compartment}`))
  const waterRow = within(outputs).getByText(river.name).closest('tr')!
  expect(waterRow.textContent).toContain(`${river.flow_type} · ${river.compartment}`)
  expect(api.elementaryFlows).toHaveBeenCalledTimes(1)
  expect(api.elementaryFlows).toHaveBeenCalledWith(river.ref.database, [fossil.ref.id, river.ref.id, 'no-such-flow'])
  expect(api.elementaryFlow).not.toHaveBeenCalled()
  expect(await screen.findByText(`Ammonia: no flow 'no-such-flow' in '${river.ref.database}'`)).toBeInTheDocument()
  expect(within(outputs).getByText(fossil.name).closest('tr')!.textContent).toContain(`${fossil.flow_type} · ${fossil.compartment}`)
})

it('returns from a supplier to the exchange that led out of the origin, at its scroll position', async () => {
  const view = renderSuppliers()
  await screen.findByText('Inputs')
  const body = view.container.querySelector('[data-scroll-body]') as HTMLElement | null
  expect(body).not.toBeNull()
  let restored: number | null = null
  Object.defineProperty(body, 'scrollTop', { configurable: true, get: () => 180, set: (value: number) => (restored = value) })
  const frameExchange = widget.exchanges.find((e) => e.input?.kind === 'foreground')!
  fireEvent.click(within(sectionOf('Inputs')).getByRole('link', { name: /frame production · foreground/ }))
  const back = await screen.findByRole('button', { name: `Back to ${widget.name}` })
  const first = screen.getByRole('button', { name: 'General information' })
  expect(back.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(back)
  await screen.findByText('Inputs')
  expect(restored).toBe(180)
  await waitFor(() => expect(sectionOf('Inputs').querySelector('tr[aria-current="true"]')?.textContent).toContain(frameExchange.name))
})

it('returns from a chain of suppliers to the destination each origin names, with browser Back left usable', async () => {
  renderSuppliers()
  await screen.findByText('Inputs')
  fireEvent.click(within(sectionOf('Inputs')).getByRole('link', { name: /frame production · foreground/ }))
  await screen.findByRole('button', { name: `Back to ${widget.name}` })
  fireEvent.click(screen.getByRole('link', { name: 'Inputs/Outputs' }))
  const frameInputs = await waitFor(() => {
    expect(sectionOf('Inputs').querySelectorAll('tr').length).toBeGreaterThan(1)
    return sectionOf('Inputs')
  })
  const steel = await within(frameInputs).findByRole('link', { name: new RegExp(backgroundProcess.value.name) })
  fireEvent.click(steel)
  fireEvent.click(await screen.findByRole('button', { name: 'Back to frame production' }))
  await screen.findByRole('button', { name: `Back to ${widget.name}` })
  expect(screen.getByRole('link', { name: 'Inputs/Outputs' })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(screen.getByRole('button', { name: 'history back' }))
  await screen.findByRole('button', { name: 'Back to frame production' })
})

it('leaves the returned exchange behind when a page tab is chosen, keeping the way back', async () => {
  const view = renderSuppliers()
  await screen.findByText('Inputs')
  fireEvent.click(within(sectionOf('Inputs')).getByRole('link', { name: /frame production · foreground/ }))
  await screen.findByRole('button', { name: `Back to ${widget.name}` })
  fireEvent.click(screen.getByRole('link', { name: 'Inputs/Outputs' }))
  const frameInputs = await waitFor(() => {
    expect(sectionOf('Inputs').querySelectorAll('tr').length).toBeGreaterThan(1)
    return sectionOf('Inputs')
  })
  const frameBody = view.container.querySelector('[data-scroll-body]') as HTMLElement
  Object.defineProperty(frameBody, 'scrollTop', { configurable: true, get: () => 120, set: () => undefined })
  fireEvent.click(await within(frameInputs).findByRole('link', { name: new RegExp(backgroundProcess.value.name) }))
  fireEvent.click(await screen.findByRole('button', { name: 'Back to frame production' }))
  await screen.findByRole('button', { name: `Back to ${widget.name}` })
  const written: number[] = []
  const body = view.container.querySelector('[data-scroll-body]') as HTMLElement
  Object.defineProperty(body, 'scrollTop', { configurable: true, get: () => 0, set: (value: number) => written.push(value) })
  fireEvent.click(screen.getByRole('link', { name: 'General information' }))
  expect(await screen.findByRole('button', { name: `Back to ${widget.name}` })).toBeInTheDocument()
  expect(written).toEqual([])
  fireEvent.click(screen.getByRole('link', { name: 'Inputs/Outputs' }))
  await screen.findByText('Inputs')
  expect(sectionOf('Inputs').querySelector('tr[aria-current="true"]')).toBeNull()
})

it('offers no way back to a supplier on a detail opened at its own address', async () => {
  renderSuppliers()
  await screen.findByText('Inputs')
  expect(screen.queryByRole('button', { name: /^Back to / })).not.toBeInTheDocument()
})

it('chooses the process it opens and asks the canvas to show its card', async () => {
  const shown: unknown[] = []
  const listen = (event: Event) => shown.push((event as CustomEvent).detail)
  window.addEventListener(CANVAS_EVENT, listen)
  useUi.setState({ chosenProcess: null })
  renderAt(`/systems/${doc.id}/processes/widget/general`, <App router={false} />)
  await waitFor(() => expect(useUi.getState().chosenProcess).toBe(widget.id))
  await waitFor(() => expect(shown).toContainEqual({ show: 'widget' }))
  window.removeEventListener(CANVAS_EVENT, listen)
})

it('puts the process pages between its title and the body they open', async () => {
  renderAt(`/systems/${doc.id}/processes/widget/general`, <App router={false} />)
  const title = await screen.findByRole('heading', { name: `General information – ${widget.name}` })
  const tabs = screen.getByRole('navigation', { name: 'Pages' })
  const section = screen.getByRole('button', { name: 'General information' }).closest('section') as HTMLElement
  expect(title.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(tabs.compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(section.closest('.overflow-auto')?.contains(tabs)).toBe(false)
})

it('keeps the pages above the rows of Inputs/Outputs and marks the open one', async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  const title = await screen.findByRole('heading', { name: `Inputs/Outputs – ${widget.name}` })
  const tabs = screen.getByRole('navigation', { name: 'Pages' })
  const inputs = await screen.findByRole('button', { name: 'Inputs' })
  expect(title.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(tabs.compareDocumentPosition(inputs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Inputs/Outputs' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: 'General information' })).not.toHaveAttribute('aria-current')
})

it('under a case the inputs show the case’s amounts and the page names it', async () => {
    const heavy = withFrameAmount(doc, 0.5)
    drawn.system = heavy
    drawn.variant = heavy
    useUi.setState({ canvasSystemId: doc.id, canvasVariant: 'heavy' })
    renderProcess()
    expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
    await screen.findByText('Inputs')
    expect(vi.mocked(api.systemAs)).toHaveBeenCalledWith(doc.id, 'heavy')
    expect(vi.mocked(api.layout).mock.calls.at(-1)?.[1]).toBe('heavy')
    const inputs = sectionOf('Inputs')
    const row = (await within(inputs).findByText('frame')).closest('tr')!
    expect(row.textContent).toContain('0.5')
    expect(row.textContent).not.toContain('0.25')
  })

  it('under base values the page names no state', async () => {
    renderProcess()
    await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
    expect(screen.queryByText(/^Under (case|scenario) /)).toBeNull()
    expect(vi.mocked(api.systemAs)).not.toHaveBeenCalled()
  })

  it('a state that cannot be read shows its refusal', async () => {
    drawn.variantFailure = new ApiError(400, { error: 'invalid', message: 'scenario heavy is behind the base', details: {} })
    useUi.setState({ canvasSystemId: doc.id, canvasVariant: 'heavy' })
    renderProcess()
    expect(await screen.findByText('case heavy cannot be read: scenario heavy is behind the base')).toBeInTheDocument()
    expect(screen.queryByText('Inputs')).toBeNull()
    expect(screen.queryByText(`Inputs/Outputs – ${widget.name}`)).toBeNull()
  })

it('leaves the revealing of the chosen card to the inspector below 768 px', async () => {
  window.innerWidth = 700
  try {
    const shown: unknown[] = []
    const listen = (event: Event) => shown.push((event as CustomEvent).detail)
    window.addEventListener(CANVAS_EVENT, listen)
    const view = renderAt(`/systems/${doc.id}`, <App router={false} />)
    const card = await waitFor(() => {
      const anchor = view.container.querySelector('.react-flow__node a') as HTMLAnchorElement | null
      expect(anchor).not.toBeNull()
      return anchor as HTMLAnchorElement
    })
    fireEvent.click(card)
    await waitFor(() => expect(useUi.getState().chosenProcess).not.toBeNull())
    expect(shown).not.toContainEqual({ show: 'widget' })
    window.removeEventListener(CANVAS_EVENT, listen)
  } finally {
    window.innerWidth = 1024
  }
})
