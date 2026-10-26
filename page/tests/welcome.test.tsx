import { screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { Answer, Database } from '@/api/types'
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
