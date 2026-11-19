import { screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, ListedDatabase, SystemRow } from '@/api/types'
import { shortHash } from '@/lib/format'
import { useUi } from '@/store/ui'
import databases from './fixtures/databases.json'
import home from './fixtures/home.json'
import sources from './fixtures/sources.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      home: vi.fn(async () => home),
      databases: vi.fn(async () => databases),
      sources: vi.fn(async () => sources),
      systems: vi.fn(),
      system: vi.fn(),
      log: vi.fn(),
      validation: vi.fn(),
    },
  }
})

const rows = home.value as SystemRow[]
const answer = home as unknown as Answer<SystemRow[]>
const none: Answer<SystemRow[]> = { value: [], hint: null, view_url: null }
const installed = databases as unknown as Answer<ListedDatabase[]>
const noDatabases = none as unknown as Answer<ListedDatabase[]>

it('lists each stored system with its database, its processes, its last change and its validation', async () => {
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  for (const row of rows) expect(await within(table).findByText(row.system.name)).toBeInTheDocument()
  expect(within(table).getAllByText(rows[0].system.database).length).toBeGreaterThan(0)
  for (const row of rows) expect(within(table).getAllByText(String(row.processes)).length).toBeGreaterThan(0)
  for (const row of rows) expect(within(table).getAllByText(new RegExp(`#${row.last.seq}`)).length).toBeGreaterThan(0)
  await waitFor(() => expect(within(table).getAllByRole('link', { name: /Valid|issue/ }).length).toBe(rows.length))
  expect(api.system).not.toHaveBeenCalled()
  expect(api.log).not.toHaveBeenCalled()
  expect(api.validation).not.toHaveBeenCalled()
})

it('says it is loading until the product systems are read', async () => {
  vi.mocked(api.home).mockImplementation(() => new Promise<never>(() => undefined))
  renderAt('/', <Screens />)
  const loading = await screen.findByRole('status')
  expect(loading).toHaveTextContent('Loading the product systems…')
  vi.mocked(api.home).mockResolvedValue(answer)
})

it('marks the row of a system whose validation cannot run, with the message as its title', async () => {
  const [kept, refused] = rows
  const failed: SystemRow = { ...refused, validation: null, unvalidated: { error: 'not_found', message: 'no database nowhere', details: {} } }
  vi.mocked(api.home).mockResolvedValue({ ...answer, value: [kept, failed] })
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  const mark = await within(table).findByRole('link', { name: '⚠ Not validated' })
  expect(mark).toHaveAttribute('title', 'no database nowhere')
  vi.mocked(api.home).mockResolvedValue(answer)
})

it('offers the sources when no database is installed', async () => {
  vi.mocked(api.home).mockResolvedValue(none)
  vi.mocked(api.databases).mockResolvedValue(noDatabases)
  renderAt('/', <Screens />)
  for (const source of sources.value) expect(await screen.findByRole('button', { name: new RegExp(source.name) })).toBeInTheDocument()
  expect(screen.queryByText(/Ask your chatbot/)).not.toBeInTheDocument()
  vi.mocked(api.home).mockResolvedValue(answer)
  vi.mocked(api.databases).mockResolvedValue(installed)
})

it('says to ask the chatbot when a database holds no system', async () => {
  vi.mocked(api.home).mockResolvedValue(none)
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  expect(await screen.findByText(/On fixture, model one bicycle frame of 2 kg of low-alloyed steel/)).toBeInTheDocument()
  vi.mocked(api.home).mockResolvedValue(answer)
})

it('holds the narrow columns of the home table on one line and gives the name the rest', async () => {
  vi.mocked(api.home).mockResolvedValue(answer)
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  await waitFor(() => expect(table.querySelectorAll('td[data-label="Name"]')).toHaveLength(rows.length))
  for (const header of ['Database', 'Processes', 'Last change', 'Validation', 'Requests']) {
    const cells = [...table.querySelectorAll(`td[data-label="${header}"]`)]
    expect(cells).toHaveLength(rows.length)
    for (const cell of cells) expect(cell.className).toContain('whitespace-nowrap')
  }
  for (const cell of table.querySelectorAll('td[data-label="Name"]')) {
    expect(cell.className).not.toContain('whitespace-nowrap')
    expect(cell.className).toContain('w-full')
  }
})

it('shows a short id beside a name two systems share, and marks the one on the canvas', async () => {
  const name = 'Cátodo de cobre — Chile (ruta pirometalúrgica)'
  const renamed = (row: SystemRow, id: string, named: string): SystemRow => ({ ...row, system: { ...row.system, id, name: named } })
  const one = renamed(rows[0], 'cc344688-1f2a-4c3d-9e4f-5a6b7c8d9e0f', name)
  const two = renamed(rows[1], '4b0d7d27-2a3b-4c5d-8e9f-0a1b2c3d4e5f', name)
  const only = renamed(rows[2], '5c1e8f30-3b4c-5d6e-9f0a-1b2c3d4e5f60', 'widget')
  vi.mocked(api.home).mockResolvedValue({ ...answer, value: [one, two, only] })
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  await waitFor(() => expect(table.querySelectorAll('td[data-label="Name"]')).toHaveLength(3))
  useUi.getState().setCanvasSystem(one.system.id)
  const [first, second, third] = [...table.querySelectorAll('td[data-label="Name"]')] as HTMLElement[]
  await waitFor(() => expect(within(first).getByText(shortHash(one.system.id))).toBeInTheDocument())
  expect(within(second).getByText(shortHash(two.system.id))).toBeInTheDocument()
  expect(within(third).queryByText(shortHash(only.system.id))).toBeNull()
  expect(within(first).getByRole('link')).toHaveAttribute('aria-current', 'true')
  expect(within(first).getByText('on the canvas')).toBeInTheDocument()
  expect(within(second).getByRole('link')).not.toHaveAttribute('aria-current')
  expect(within(second).queryByText('on the canvas')).toBeNull()
  vi.mocked(api.home).mockResolvedValue(answer)
})
