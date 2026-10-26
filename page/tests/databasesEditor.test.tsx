import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api, ApiError } from '@/api/client'
import type { Answer, DatabaseSource, Install } from '@/api/types'
import databases from './fixtures/databases.json'
import installs from './fixtures/installs.json'
import server from './fixtures/server.json'
import sources from './fixtures/sources.json'
import { renderAt } from './render'

const listed = installs as unknown as Answer<Install[]>
const offered = sources as unknown as Answer<DatabaseSource[]>

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      databases: vi.fn(async () => databases),
      sources: vi.fn(async () => offered),
      installs: vi.fn(async () => listed),
      server: vi.fn(async () => server),
      postInstall: vi.fn(async () => ({ value: listed.value[0], hint: null, view_url: null })),
      cancelInstall: vi.fn(async () => ({ value: listed.value[0], hint: null, view_url: null })),
      putCredential: vi.fn(async () => undefined),
      uploadDatabase: vi.fn(async () => ({ value: listed.value[0], hint: null, view_url: null })),
    },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.sources).mockResolvedValue(offered)
  vi.mocked(api.installs).mockResolvedValue(listed)
  vi.mocked(api.postInstall).mockResolvedValue({ value: listed.value[0], hint: null, view_url: null })
})

async function pick(name: string) {
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(name) }))
}

it('lists the installed databases and the sources', async () => {
  renderAt('/databases', <Screens />)
  const table = await screen.findByRole('table')
  for (const database of databases.value) {
    expect(await within(table).findByText(database.name)).toBeInTheDocument()
    expect(within(table).getAllByText(database.version).length).toBeGreaterThan(0)
    expect(within(table).getByText(database.fingerprint.slice(0, 12))).toBeInTheDocument()
  }
  for (const source of offered.value) expect(await screen.findByRole('button', { name: new RegExp(source.name) })).toBeInTheDocument()
})

it("asks for an account only when the source's is not held", async () => {
  vi.mocked(api.sources).mockResolvedValue({
    ...offered,
    value: offered.value.map((source) => (source.name === 'bafu' ? { ...source, held: false } : source)),
  })
  vi.mocked(api.installs).mockResolvedValue({ ...listed, value: [] })
  renderAt('/databases', <Screens />)
  await pick('bafu')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Install' })).toBeInTheDocument())
  fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'carlos' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Install' }))
  await waitFor(() => expect(api.putCredential).toHaveBeenCalledWith('nexus', { username: 'carlos', password: 'a secret', token: undefined }))
  await waitFor(() => expect(api.postInstall).toHaveBeenCalled())
  expect(vi.mocked(api.putCredential).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.postInstall).mock.invocationCallOrder[0])
  await pick('ecoinvent')
  await waitFor(() => expect(screen.getByLabelText('System model')).toBeInTheDocument())
  expect(screen.queryByLabelText('Username')).not.toBeInTheDocument()
})

async function openAnUnheldAccount(name: string, username: string, password: string) {
  vi.mocked(api.sources).mockResolvedValue({
    ...offered,
    value: offered.value.map((source) => (source.name === name ? { ...source, held: false } : source)),
  })
  vi.mocked(api.installs).mockResolvedValue({ ...listed, value: [] })
  renderAt('/databases', <Screens />)
  await pick(name)
  fireEvent.change(await screen.findByLabelText('Username'), { target: { value: username } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
}

it('adds credentials without installing', async () => {
  await openAnUnheldAccount('ecoinvent', 'carlos', 'a secret')
  fireEvent.click(screen.getByRole('button', { name: 'Add credentials' }))
  await waitFor(() =>
    expect(api.putCredential).toHaveBeenCalledWith('ecoinvent', { username: 'carlos', password: 'a secret', token: undefined }),
  )
  expect(api.postInstall).not.toHaveBeenCalled()
})

it('installs with the credentials entered', async () => {
  await openAnUnheldAccount('ecoinvent', 'carlos', 'a secret')
  fireEvent.click(screen.getByRole('button', { name: 'Install' }))
  await waitFor(() =>
    expect(api.putCredential).toHaveBeenCalledWith('ecoinvent', { username: 'carlos', password: 'a secret', token: undefined }),
  )
  await waitFor(() => expect(api.postInstall).toHaveBeenCalledWith(expect.objectContaining({ source: 'ecoinvent' })))
  expect(vi.mocked(api.putCredential).mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(api.postInstall).mock.invocationCallOrder[0],
  )
})

it('uploads the openLCA zip a person holds', async () => {
  renderAt('/databases', <Screens />)
  await pick('openlca')
  const file = new File(['zip'], 'database.zip', { type: 'application/zip' })
  fireEvent.change(await screen.findByLabelText('The zip you hold'), { target: { files: [file] } })
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'a database held' } })
  fireEvent.change(screen.getByLabelText('Version'), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Upload' }))
  await waitFor(() => expect(api.uploadDatabase).toHaveBeenCalled())
  const form = vi.mocked(api.uploadDatabase).mock.calls[0][0]
  expect(form.get('file')).toBe(file)
  expect(form.get('name')).toBe('a database held')
  expect(form.get('version')).toBe('1')
})

it('shows the terms of an install that stopped at them and posts again once ticked', async () => {
  renderAt('/databases', <Screens />)
  await pick('bafu')
  const terms = listed.value[0].terms!
  expect(await screen.findByText(terms.citation)).toBeInTheDocument()
  const licence = screen.getByRole('link', { name: /terms/i })
  expect(licence.getAttribute('href')).toContain(`/api/installs/${listed.value[0].id}/licence`)
  const installButton = screen.getByRole('button', { name: 'Install' })
  expect(installButton).toBeDisabled()
  fireEvent.click(screen.getByLabelText(/accept the terms/i))
  expect(installButton).toBeEnabled()
  fireEvent.click(installButton)
  await waitFor(() => expect(api.postInstall).toHaveBeenCalledWith(expect.objectContaining({ source: 'bafu', accept_terms: true })))
})

it("shows an open install's step and cancels it", async () => {
  const open: Install = {
    ...listed.value[0],
    status: 'running',
    open: true,
    progress: { step: 'compiling the arrays', count: 42 },
    started_at: new Date(Date.now() - 3 * 60_000).toISOString(),
    terms: null,
  }
  vi.mocked(api.installs).mockResolvedValue({ ...listed, value: [open] })
  renderAt('/databases', <Screens />)
  expect(await screen.findByText('compiling the arrays')).toBeInTheDocument()
  expect(screen.getByText('42')).toBeInTheDocument()
  expect(screen.getByText(/min ago/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(api.cancelInstall).toHaveBeenCalledWith(open.id))
})

it("shows a refusal's message and hint", async () => {
  vi.mocked(api.postInstall).mockRejectedValue(
    new ApiError(503, {
      error: 'unavailable',
      message: 'bafu installs from an account this server does not hold',
      details: { hint: 'set NEXUS_USERNAME and NEXUS_PASSWORD' },
    }),
  )
  renderAt('/databases', <Screens />)
  await pick('uslci')
  fireEvent.click(await screen.findByRole('button', { name: 'Install' }))
  expect(await screen.findByText('bafu installs from an account this server does not hold')).toBeInTheDocument()
  expect(screen.getByText('set NEXUS_USERNAME and NEXUS_PASSWORD')).toBeInTheDocument()
})
