import { screen, waitFor, within } from '@testing-library/react'
import { useUi } from '@/store/ui'
import { CANVAS_EVENT } from '@/window/shortcuts'
import { renderAt } from './render'
import { App } from '@/App'
import { api } from '@/api/client'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import backgroundProcess from './fixtures/background_process.json'
import type { ProductSystem, SystemRead } from '@/api/types'

const doc = system.value as ProductSystem
const widget = doc.processes.find((p) => p.code === 'widget')!
const co2 = widget.exchanges.find((e) => e.type === 'elementary')!
const steel = widget.exchanges.find((e) => e.type === 'product' && e.input?.kind === 'background' && e.name === 'steel')!

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      elementaryFlow: vi.fn(async () => ({ ...elementaryFlow, value: { ...elementaryFlow.value, name: co2.name, side: 'output', flow_type: 'inventory indicator' } })),
      backgroundProcess: vi.fn(async () => backgroundProcess),
    },
  }
})

it('shows the emission under Outputs once its side is answered, naming its flow type', async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  await waitFor(() => expect(screen.getAllByText(co2.name).length).toBeGreaterThan(0))
  const outputs = screen.getByText('Outputs').closest('section')!
  expect(outputs.textContent).toContain(co2.name)
  expect(outputs.textContent).toContain(widget.reference_product)
  // a bundle files a natural resource under openLCA's "Resource"
  expect(outputs.textContent).toContain('inventory indicator · Resource')
})

it("shows a background input's provider as the background process's name and location", async () => {
  renderAt(`/systems/${doc.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  const inputs = screen.getByText('Inputs').closest('section')!
  await waitFor(() => expect(inputs.textContent).toContain(`${backgroundProcess.value.name} · ${backgroundProcess.value.location}`))
  expect(inputs.textContent).toContain(steel.name)
})

it('shows a linked input as the system it links, linking to that system', async () => {
  const link = { ...steel, id: 'link-exchange', name: 'frame kit', input: { kind: 'system' as const, product_system_id: 'frame-system', at_hash: 'a'.repeat(64), case: null } }
  const linking = { ...doc, id: 'linking-system', processes: doc.processes.map((p) => (p.code === 'widget' ? { ...p, exchanges: [...p.exchanges, link] } : p)) }
  vi.mocked(api.system).mockImplementation(async (id) => (id === linking.id ? { ...(system as SystemRead), value: linking } : (system as SystemRead)))
  renderAt(`/systems/${linking.id}/processes/widget/io`, <App router={false} />)
  await waitFor(() => expect(screen.getByText(`Inputs/Outputs – ${widget.name}`)).toBeInTheDocument())
  const inputs = screen.getByText('Inputs').closest('section')!
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
