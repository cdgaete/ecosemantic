import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import { api } from '@/api/client'
import { renderAt } from './render'
import { firstMethodOf } from './method'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'

const first = { ...inventory, has_more: true, next_cursor: '100', hint: "more results; call again with cursor='100'" }
const second = { ...inventory, items: inventory.items.map((item) => ({ ...item, name: `${item.name}, second page` })), has_more: false, next_cursor: null, hint: null }

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
      inventory: vi.fn(async (_id: string, body: { cursor?: string }) => (body.cursor === '100' ? second : first)),
    },
  }
})

const search = `?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}`

it('folds the columns the panel cannot hold under the flow name', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  const section = (await screen.findByText('Outputs')).closest('section')!
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
  expect(folded.map((el) => el.textContent?.trim())).toEqual([`Compartment: ${item.compartment}`, 'Sub-compartment:', `Dominant process: ${item.source?.code}`])
})

it('pages the inventory forward and back, with its pager rather than the cursor hint', async () => {
  renderAt(`/systems/${system.value.id}/results/inventory${search}`, <App router={false} />)
  // the page reads the inventory again once the system's hash arrives; page after that read
  await waitFor(() => expect(vi.mocked(api.inventory)).toHaveBeenCalledTimes(2))
  fireEvent.click(await screen.findByText('Next page'))
  expect(screen.queryByText(/call again with cursor/)).not.toBeInTheDocument()
  await waitFor(() => expect(vi.mocked(api.inventory).mock.calls.at(-1)?.[1].cursor).toBe('100'))
  const name = inventory.items[0].name
  await screen.findByText(`${name}, second page`)
  fireEvent.click(await screen.findByText('Previous page'))
  await screen.findByText(name)
  expect(screen.queryByText('Previous page')).not.toBeInTheDocument()
})
