import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { App } from '@/App'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      version: vi.fn(async () => system.value),
      log: vi.fn(async () => log),
    },
  }
})

const hash = system.value.hash as string

describe('version editor', () => {
  it('keeps every page tab inside the version and marks the open one active', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}/parameters`, <App router={false} />)
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Pages' })).toBeInTheDocument())
    const nav = screen.getByRole('navigation', { name: 'Pages' })
    const links = within(nav).getAllByRole('link')
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) expect(link.getAttribute('href')).toContain(`/systems/${system.value.id}/versions/${hash}`)
    expect(within(nav).getByText('Parameters')).toHaveAttribute('aria-current', 'page')
  })

  it('names the log entry at that hash in the read-only banner', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`entry #${log.value[0].seq}`, { exact: false })).toBeInTheDocument())
    expect(screen.getByText(log.value[0].message, { exact: false })).toBeInTheDocument()
  })

  it('says so when no log entry carries the hash on screen', async () => {
    renderAt(`/systems/${system.value.id}/versions/deadbeef`, <App router={false} />)
    await waitFor(() => expect(screen.getByText('No log entry names this hash.', { exact: false })).toBeInTheDocument())
  })

  it('says validation answers for the current document in place of the reference and validation rows', async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`General information – ${system.value.name}`)).toBeInTheDocument())
    const line = screen.getByText('Validation answers for the current document, not for this version.')
    const link = within(line.parentElement!).getByRole('link', { name: 'Open the live product system' })
    expect(link.getAttribute('href')).toBe(`/systems/${system.value.id}`)
    expect(screen.queryByText('Reference')).toBeNull()
    expect(screen.queryByText('Target amount')).toBeNull()
  })

  it("leaves the validation rows and section off a version's Statistics page", async () => {
    renderAt(`/systems/${system.value.id}/versions/${hash}/statistics`, <App router={false} />)
    await waitFor(() => expect(screen.getByText(`Statistics – ${system.value.name}`)).toBeInTheDocument())
    expect(screen.getByText('Validation answers for the current document, not for this version.')).toBeInTheDocument()
    expect(screen.queryByText('Connected graph / can calculate?')).toBeNull()
    expect(screen.queryByText('Reference process')).toBeNull()
    expect(screen.queryByText('Validation')).toBeNull()
    expect(screen.getByText('Number of processes')).toBeInTheDocument()
  })
})
