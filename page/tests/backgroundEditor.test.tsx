import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App } from '@/App'
import { api } from '@/api/client'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import backgroundProcess from './fixtures/background_process.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import type { Answer, BackgroundExchange, BackgroundProcess } from '@/api/types'

const answer = backgroundProcess as Answer<BackgroundProcess>
const process = answer.value
const URL = 'https://ecoquery.ecoinvent.org/3.12/cutoff/dataset/275867/documentation'
const SUPPLIER = '4a018168-2ca8-56de-a7f7-c7ce8f6a5040_81c36885-6d13-58e3-ba9a-869123a0f84c'
const read = (ref: string, url: string | null) => ({ ...answer, value: { ...process, ref: { ...process.ref, id: ref }, url } })

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      backgroundProcess: vi.fn(async () => answer),
      elementaryFlow: vi.fn(async () => elementaryFlow),
    },
  }
})

it("shows the dataset's publication link as a Source row that opens in a new tab", async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue(read(`${process.ref.id}-linked`, URL))
  renderAt(`/databases/fixture/processes/${process.ref.id}-linked`, <App router={false} />)
  const link = await screen.findByRole('link', { name: URL })
  expect(link).toHaveAttribute('href', URL)
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noreferrer')
  expect(screen.getByText('Source')).toBeInTheDocument()
})

it('shows no Source row for a dataset with no publication link', async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue(read(`${process.ref.id}-plain`, null))
  renderAt(`/databases/fixture/processes/${process.ref.id}-plain`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('General information')).toBeInTheDocument())
  expect(screen.getAllByText(process.name).length).toBeGreaterThan(0)
  expect(screen.getByText('Comment')).toBeInTheDocument()
  expect(screen.queryByText('Source')).not.toBeInTheDocument()
})

it('shows an empty Location field for a dataset that names no location', async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue({
    ...answer,
    value: { ...process, ref: { ...process.ref, id: `${process.ref.id}-unplaced` }, location: null },
  })
  renderAt(`/databases/fixture/processes/${process.ref.id}-unplaced`, <App router={false} />)
  const label = await screen.findByText('Location')
  expect(label.nextElementSibling?.textContent).toBe('')
  expect(screen.queryByText('null')).not.toBeInTheDocument()
})

it('shows the exchanges as an Inputs table and an Outputs table of flow, amount, unit and provider', async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue(answer)
  renderAt(`/databases/fixture/processes/${process.ref.id}`, <App router={false} />)
  const inputs = (await screen.findByText('Inputs')).closest('section')!
  const outputs = screen.getByText('Outputs').closest('section')!
  for (const table of [inputs, outputs]) {
    for (const header of ['Flow', 'Amount', 'Unit', 'Provider']) {
      expect(within(table).getByText(header)).toBeInTheDocument()
    }
    expect(within(table).queryByText('Type')).not.toBeInTheDocument()
  }
  expect(inputs.textContent).toContain('electricity')
  expect(outputs.textContent).toContain('steel')
  expect(inputs.textContent).not.toContain('steel')
})

it("puts the reference output first in Outputs, in bold, and links a product to its supplier's dataset", async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue(answer)
  renderAt(`/databases/fixture/processes/${process.ref.id}`, <App router={false} />)
  const outputs = (await screen.findByText('Outputs')).closest('section')!
  const rows = within(outputs).getAllByRole('row').slice(1)
  expect(rows[0].textContent).toContain('steel')
  expect(rows[0].className).toContain('font-semibold')
  expect(rows.slice(1).filter((row) => row.className.includes('font-semibold'))).toEqual([])
  const inputs = screen.getByText('Inputs').closest('section')!
  const link = within(inputs).getByRole('link', { name: 'electricity production' })
  expect(link).toHaveAttribute('href', `/databases/fixture/processes/${SUPPLIER}`)
})

it("shows an elementary flow's provider as its flow type and compartment", async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue(answer)
  renderAt(`/databases/fixture/processes/${process.ref.id}`, <App router={false} />)
  const outputs = (await screen.findByText('Outputs')).closest('section')!
  const row = within(outputs).getByText('Carbon dioxide, fossil').closest('tr')!
  await waitFor(() => expect(row.textContent).toContain(`${elementaryFlow.value.flow_type} · ${elementaryFlow.value.compartment}`))
})

it('shows an input the install cut off in Inputs with its reason and no provider', async () => {
  const cutOff: BackgroundExchange = {
    amount: 0.25,
    cut_off: 'no provider for the input',
    flow: 'sand',
    input: null,
    reference: false,
    side: 'input',
    supplier: null,
    type: 'product',
    unit: 'kilogram',
  }
  vi.mocked(api.backgroundProcess).mockResolvedValue({
    ...answer,
    value: { ...process, exchanges: [...(process.exchanges ?? []), cutOff] },
  })
  renderAt(`/databases/fixture/processes/${process.ref.id}-cut`, <App router={false} />)
  const inputs = (await screen.findByText('Inputs')).closest('section')!
  const reason = within(inputs).getByText('cut off: no provider for the input')
  expect(reason).toHaveClass('text-muted-foreground')
  const row = reason.closest('tr')!
  expect(row.textContent).toContain('sand')
  expect(row.textContent).toContain('0.25')
  expect(within(row).queryByRole('link')).not.toBeInTheDocument()
})
