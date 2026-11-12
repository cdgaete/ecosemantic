import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useUi } from '@/store/ui'
import { CANVAS_EVENT } from '@/window/shortcuts'
import { renderAt } from './render'
import { layoutAnswer } from './placements'
import { App } from '@/App'
import { ApiError, api } from '@/api/client'
import type { Answer, Arrangement, Process, ProductSystem, SystemRead } from '@/api/types'
import { InputsOutputsPage } from '@/editors/process/InputsOutputsPage'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import backgroundProcess from './fixtures/background_process.json'

const doc = system.value as ProductSystem
const widget = doc.processes.find((p) => p.code === 'widget')!
const co2 = widget.exchanges.find((e) => e.type === 'elementary')!
const steel = widget.exchanges.find((e) => e.type === 'product' && e.input?.kind === 'background' && e.name === 'steel')!

const drawn = vi.hoisted(() => ({ system: null as unknown as ProductSystem, held: null as Promise<Answer<Arrangement>> | null, failure: null as Error | null }))

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
      elementaryFlow: vi.fn(async () => ({ ...elementaryFlow, value: { ...elementaryFlow.value, name: co2.name, side: 'output', flow_type: 'inventory indicator' } })),
      backgroundProcess: vi.fn(async () => backgroundProcess),
    },
  }
})

beforeEach(() => {
  drawn.system = doc
  drawn.held = null
  drawn.failure = null
})

function renderRows(product: ProductSystem = doc, process: Process = widget) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/systems/${product.id}/processes/${process.code}/io`]}>
        <TooltipProvider>
          <InputsOutputsPage systemId={product.id} system={product} process={process} />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const sectionOf = (title: string) => screen.getByText(title).closest('section') as HTMLElement
const rowsOf = (title: string) => Array.from(sectionOf(title).querySelectorAll('tbody tr')).map((row) => row.textContent ?? '')

it('names the flow type and compartment of an elementary flow once the flow is answered', async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  const outputs = sectionOf('Outputs')
  await waitFor(() => expect(outputs.textContent).toContain('inventory indicator · Resource'))
  expect(outputs.textContent).toContain(co2.name)
  expect(outputs.textContent).toContain(widget.reference_product)
})

it('lists the rows of each section in the order its placement gives', async () => {
  const base = layoutAnswer(doc)
  const cards = base.value.cards.map((card) => (card.code === 'widget' ? { ...card, inputs: [...card.inputs].reverse(), outputs: [...card.outputs].reverse() } : card))
  drawn.held = Promise.resolve({ ...base, value: { ...base.value, cards } })
  renderRows()
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  const inputs = await waitFor(() => {
    expect(rowsOf('Inputs').length).toBeGreaterThan(1)
    return rowsOf('Inputs')
  })
  expect(inputs[0]).toContain('frame')
  expect(inputs[inputs.length - 1]).toContain(steel.name)
  const outputs = rowsOf('Outputs')
  expect(outputs[0]).toContain(co2.name)
  expect(outputs[1]).toContain(widget.reference_product)
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
  const inputs = sectionOf('Inputs')
  await waitFor(() => expect(inputs.textContent).toContain(`${backgroundProcess.value.name} · ${backgroundProcess.value.location}`))
  expect(inputs.textContent).toContain(steel.name)
})

it('shows a linked input as the system it links, linking to that system', async () => {
  const link = { ...steel, id: 'link-exchange', name: 'frame kit', input: { kind: 'system' as const, product_system_id: 'frame-system', at_hash: 'a'.repeat(64), case: null } }
  const linking = { ...doc, id: 'linking-system', processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, link] } : p)) }
  drawn.system = linking
  vi.mocked(api.system).mockImplementation(async (id) => (id === linking.id ? { ...(system as SystemRead), value: linking } : (system as SystemRead)))
  renderAt(`/systems/${linking.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  const inputs = sectionOf('Inputs')
  expect(within(inputs).getByRole('link', { name: 'frame kit · linked system' })).toHaveAttribute('href', '/systems/frame-system')
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
