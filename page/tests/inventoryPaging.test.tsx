import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import { api } from '@/api/client'
import type { InventoryListing, Side } from '@/api/types'
import { renderAt } from './render'
import { firstMethodOf } from './method'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'

const linked = {
  kind: 'linked' as const,
  product_system_id: 'frame-system',
  at_hash: 'ab'.repeat(32),
  code: 'part',
}
const pinned = {
  ...system.value,
  name: 'frame system',
  processes: [{ ...system.value.processes[0], code: 'part', name: 'part machining', location: 'CL' }],
}

const drawn = (name: string, amount: number) => ({
  ...inventory.items[0],
  name,
  amount,
  side: 'input',
  compartment: 'natural resource',
  flow_type: 'natural resource',
  unit: 'cubic meter',
})
const sides: Record<Side, (typeof inventory.items)[number][]> = {
  input: [drawn('Water, river', 12), drawn('Water, well', 3)],
  output: inventory.items,
}

// one row a page, so each table's pager has a next page to ask for
const pageOf = (side: Side, cursor?: string) => {
  const rows = sides[side]
  const at = cursor === undefined ? 0 : Number(cursor)
  const more = at + 1 < rows.length
  return {
    ...inventory,
    items: rows.slice(at, at + 1),
    has_more: more,
    next_cursor: more ? String(at + 1) : null,
    hint: null,
  }
}

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      validation: vi.fn(async () => validation),
      vocabulary: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      impact: vi.fn(async () => impact),
      inventory: vi.fn(async (_id: string, body: { side?: Side; cursor?: string }) => pageOf(body.side ?? 'output', body.cursor)),
      version: vi.fn(async () => pinned),
    },
  }
})

const search = `?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}`

const asked = (side: Side) => vi.mocked(api.inventory).mock.calls.map((call) => call[1]).filter((body) => body.side === side)

const sectionNamed = async (title: string) => (await screen.findByText(title)).closest('section')!

it('folds the columns the panel cannot hold under the flow name', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  const section = await sectionNamed('Outputs')
  const table = await waitFor(() => within(section).getByRole('table'))
  await waitFor(() => expect(within(table).getByText(inventory.items[0].name)).toBeInTheDocument())
  for (const name of ['Compartment', 'Sub-compartment', 'Dominant process']) expect(within(table).getByRole('columnheader', { name })).toHaveClass('hidden', '@lg:table-cell')
  for (const name of ['Name', 'Amount', 'Unit']) expect(within(table).getByRole('columnheader', { name })).not.toHaveClass('hidden')
  const row = within(table).getAllByRole('row')[1]
  const cells = within(row).getAllByRole('cell')
  expect(cells[1]).toHaveClass('hidden', '@lg:table-cell')
  expect(cells[2]).toHaveClass('hidden', '@lg:table-cell')
  expect(cells[5]).toHaveClass('hidden', '@lg:table-cell')
  const item = inventory.items[0]
  const folded = [...cells[0].children].filter((el) => el.className.includes('@lg:hidden'))
  expect(folded.map((el) => el.textContent?.trim())).toEqual([`Compartment: ${item.compartment}`, 'Sub-compartment:', 'Dominant process: widget assembly · GLO'])
})

it('pages each of the two tables on its own', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  const inputs = await sectionNamed('Inputs')
  const outputs = await sectionNamed('Outputs')
  await waitFor(() => expect(within(outputs).getByText(inventory.items[0].name)).toBeInTheDocument())
  await waitFor(() => expect(within(inputs).getByText('Water, river')).toBeInTheDocument())

  fireEvent.click(within(outputs).getByText('Next page'))
  await waitFor(() => expect(within(outputs).getByText(inventory.items[1].name)).toBeInTheDocument())
  expect(within(inputs).getByText('Water, river')).toBeInTheDocument()
  expect(asked('input').every((body) => body.cursor === undefined)).toBe(true)
  expect(within(inputs).getByText('Next page')).toBeInTheDocument()

  fireEvent.click(within(inputs).getByText('Next page'))
  await waitFor(() => expect(within(inputs).getByText('Water, well')).toBeInTheDocument())
  expect(within(outputs).getByText(inventory.items[1].name)).toBeInTheDocument()
  expect(asked('input').at(-1)?.cursor).toBe('1')
  expect(asked('output').at(-1)?.cursor).toBe('1')

  fireEvent.click(within(outputs).getByText('Previous page'))
  await waitFor(() => expect(within(outputs).getByText(inventory.items[0].name)).toBeInTheDocument())
  expect(within(inputs).getByText('Water, well')).toBeInTheDocument()
  expect(within(inputs).getByText('Previous page')).toBeInTheDocument()
  expect(within(inputs).queryByText(/call again with cursor/)).not.toBeInTheDocument()
})

it('asks for the largest amount first when the order is picked', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  await waitFor(() => expect(asked('output').length).toBeGreaterThan(0))
  expect(asked('output').every((body) => body.order === 'compartment')).toBe(true)
  fireEvent.change(screen.getByLabelText('Order'), { target: { value: 'amount' } })
  await waitFor(() => expect(asked('output').at(-1)?.order).toBe('amount'))
  expect(asked('output').at(-1)?.cursor).toBeUndefined()
  expect(asked('input').at(-1)?.order).toBe('amount')
})

const dominant = (row: HTMLElement) => within(row).getAllByRole('cell')[5]

it('the dominant process is named', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  const outputs = await sectionNamed('Outputs')
  await waitFor(() => expect(within(outputs).getByText(inventory.items[0].name)).toBeInTheDocument())
  expect(dominant(within(outputs).getAllByRole('row')[1])).toHaveTextContent('widget assembly · GLO')
  expect(dominant(within(outputs).getAllByRole('row')[1]).querySelector('[title="widget"]')).not.toBeNull()
  fireEvent.click(within(outputs).getByText('Next page'))
  await waitFor(() => expect(within(outputs).getByText(inventory.items[1].name)).toBeInTheDocument())
  const frame = dominant(within(outputs).getAllByRole('row')[1])
  expect(frame).toHaveTextContent('frame production · GLO')
  expect(frame.querySelector('[title="frame"]')).not.toBeNull()
})

it('a linked source is named from the version its link pins', async () => {
  vi.mocked(api.inventory).mockImplementation(async (_id: string, body: { side?: Side; cursor?: string }) => {
    const page = pageOf(body.side ?? 'output', body.cursor)
    return { ...page, items: page.items.map((row) => ({ ...row, source: linked })) } as InventoryListing
  })
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'linked' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  const outputs = await sectionNamed('Outputs')
  await waitFor(() => expect(within(outputs).getByText(inventory.items[0].name)).toBeInTheDocument())
  await waitFor(() => expect(dominant(within(outputs).getAllByRole('row')[1])).toHaveTextContent('part machining · CL'))
})
