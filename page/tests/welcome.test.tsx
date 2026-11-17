import { screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, Database } from '@/api/types'
import { shortHash } from '@/lib/format'
import { useUi } from '@/store/ui'
import databases from './fixtures/databases.json'
import log from './fixtures/log.json'
import sources from './fixtures/sources.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      sources: vi.fn(async () => sources),
      system: vi.fn(async () => system),
      log: vi.fn(async () => log),
      validation: vi.fn(async () => validation),
    },
  }
})

it('lists each stored system with its database, its processes, its last change and its validation', async () => {
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  for (const card of systems.value) expect(await within(table).findByText(card.name)).toBeInTheDocument()
  expect(within(table).getAllByText(systems.value[0].database).length).toBeGreaterThan(0)
  await waitFor(() => expect(within(table).getAllByText(String(system.value.processes.length)).length).toBe(systems.value.length))
  const last = log.value.at(-1)!
  await waitFor(() => expect(within(table).getAllByText(new RegExp(`#${last.seq}`)).length).toBe(systems.value.length))
  await waitFor(() => expect(within(table).getAllByRole('link', { name: /Valid|issue/ }).length).toBe(systems.value.length))
})

const none = { value: [], hint: null, view_url: null }
const installed = databases as unknown as Answer<Database[]>

it('offers the sources when no database is installed', async () => {
  vi.mocked(api.systems).mockResolvedValue(none)
  vi.mocked(api.databases).mockResolvedValue(none)
  renderAt('/', <Screens />)
  for (const source of sources.value) expect(await screen.findByRole('button', { name: new RegExp(source.name) })).toBeInTheDocument()
  expect(screen.queryByText(/Ask your chatbot/)).not.toBeInTheDocument()
})

it('says to ask the chatbot when a database holds no system', async () => {
  vi.mocked(api.systems).mockResolvedValue(none)
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  expect(await screen.findByText(/On fixture, model one bicycle frame of 2 kg of low-alloyed steel/)).toBeInTheDocument()
})

it('holds the narrow columns of the home table on one line and gives the name the rest', async () => {
  vi.mocked(api.systems).mockResolvedValue(systems)
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  await waitFor(() => expect(table.querySelectorAll('td[data-label="Name"]')).toHaveLength(systems.value.length))
  for (const header of ['Database', 'Processes', 'Last change', 'Validation', 'Requests']) {
    const cells = [...table.querySelectorAll(`td[data-label="${header}"]`)]
    expect(cells).toHaveLength(systems.value.length)
    for (const cell of cells) expect(cell.className).toContain('whitespace-nowrap')
  }
  for (const cell of table.querySelectorAll('td[data-label="Name"]')) {
    expect(cell.className).not.toContain('whitespace-nowrap')
    expect(cell.className).toContain('w-full')
  }
})

it('shows a short id beside a name two systems share, and marks the one on the canvas', async () => {
  const name = 'Cátodo de cobre — Chile (ruta pirometalúrgica)'
  const one = { ...systems.value[0], id: 'cc344688-1f2a-4c3d-9e4f-5a6b7c8d9e0f', name }
  const two = { ...systems.value[1], id: '4b0d7d27-2a3b-4c5d-8e9f-0a1b2c3d4e5f', name }
  const only = { ...systems.value[2], id: '5c1e8f30-3b4c-5d6e-9f0a-1b2c3d4e5f60', name: 'widget' }
  vi.mocked(api.systems).mockResolvedValue({ ...systems, value: [one, two, only] } as unknown as typeof systems)
  vi.mocked(api.databases).mockResolvedValue(installed)
  renderAt('/', <Screens />)
  const table = await screen.findByRole('table')
  await waitFor(() => expect(table.querySelectorAll('td[data-label="Name"]')).toHaveLength(3))
  useUi.getState().setCanvasSystem(one.id)
  const [first, second, third] = [...table.querySelectorAll('td[data-label="Name"]')] as HTMLElement[]
  await waitFor(() => expect(within(first).getByText(shortHash(one.id))).toBeInTheDocument())
  expect(within(second).getByText(shortHash(two.id))).toBeInTheDocument()
  expect(within(third).queryByText(shortHash(only.id))).toBeNull()
  expect(within(first).getByRole('link')).toHaveAttribute('aria-current', 'true')
  expect(within(first).getByText('on the canvas')).toBeInTheDocument()
  expect(within(second).getByRole('link')).not.toHaveAttribute('aria-current')
  expect(within(second).queryByText('on the canvas')).toBeNull()
  vi.mocked(api.systems).mockResolvedValue(systems)
})
