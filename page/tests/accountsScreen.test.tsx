import { focusManager } from '@tanstack/react-query'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Screens } from '@/App'
import { api } from '@/api/client'
import type { AccountEntry, Answer, DatabaseSource } from '@/api/types'
import sources from './fixtures/sources.json'
import { renderAt } from './render'

const offered = sources as unknown as Answer<DatabaseSource[]>

const WHY =
  'This page reaches EcoSemantic through the bridge. Database accounts are entered on the computer where EcoSemantic runs, so the password stays on that computer and never passes through the internet or a chat.'
const TRAY =
  'On the computer where EcoSemantic runs, click the EcoSemantic icon beside the clock in the taskbar (it may sit under the ^ arrow) and choose Database accounts…'
const KEPT = 'Kept on this computer until EcoSemantic restarts.'
const NOT_SAVED = 'Not saved'
const SAVED = 'Saved until EcoSemantic restarts'
const PAGE = 'https://carlosgaete.bridge.ecosemantic.com'
const HERE: AccountEntry = { reach: 'here', here: true, why: null, steps: null, page: null }
const BRIDGED: AccountEntry = { reach: 'bridge', here: false, why: WHY, steps: TRAY, page: PAGE }

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      sources: vi.fn(async () => offered),
      credentials: vi.fn(async () => ({ held: [] })),
      accountEntry: vi.fn(async () => HERE),
      putCredential: vi.fn(async () => null),
      deleteCredential: vi.fn(async () => null),
    },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.sources).mockResolvedValue(offered)
  vi.mocked(api.credentials).mockResolvedValue({ held: [] })
  vi.mocked(api.accountEntry).mockResolvedValue(HERE)
})

it('shows one card per kind of account the sources need', async () => {
  renderAt('/accounts', <Screens />)
  const nexus = await screen.findByRole('region', { name: 'Nexus' })
  const ecoinvent = screen.getByRole('region', { name: 'ecoinvent' })
  expect(within(nexus).getByRole('heading', { name: 'Nexus' })).toBeInTheDocument()
  expect(within(ecoinvent).getByRole('heading', { name: 'ecoinvent' })).toBeInTheDocument()
  expect(within(nexus).getByText('Opens bafu.')).toBeInTheDocument()
  expect(within(ecoinvent).getByText('Opens ecoinvent.')).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'uslci' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'openlca' })).not.toBeInTheDocument()
  for (const card of [nexus, ecoinvent]) {
    expect(within(card).getByText(NOT_SAVED)).toBeInTheDocument()
    expect(within(card).getByText(KEPT)).toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /navigation/ })).not.toBeInTheDocument()
  expect(document.title).toBe('Database accounts — EcoSemantic')
})

it('names each card as the sources answer its account', async () => {
  vi.mocked(api.sources).mockResolvedValue({
    ...offered,
    value: offered.value.map((source) => (source.account === null ? source : { ...source, account: { ...source.account, name: `${source.account.name} as answered` } })),
  })
  renderAt('/accounts', <Screens />)
  const nexus = await screen.findByRole('region', { name: 'Nexus as answered' })
  expect(within(nexus).getByRole('heading', { name: 'Nexus as answered' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'ecoinvent as answered' })).toBeInTheDocument()
})

it('saves and removes an account', async () => {
  renderAt('/accounts', <Screens />)
  const card = await screen.findByRole('region', { name: 'Nexus' })
  fireEvent.change(within(card).getByLabelText('Username'), { target: { value: 'carlos' } })
  fireEvent.change(within(card).getByLabelText('Password'), { target: { value: 'a secret' } })
  fireEvent.change(within(card).getByLabelText('Token'), { target: { value: 'a token' } })
  vi.mocked(api.credentials).mockResolvedValue({ held: ['nexus'] })
  fireEvent.click(within(card).getByRole('button', { name: 'Save' }))
  await waitFor(() =>
    expect(api.putCredential).toHaveBeenCalledWith('nexus', { username: 'carlos', password: 'a secret', token: 'a token' }),
  )
  expect(await within(card).findByText(SAVED)).toBeInTheDocument()
  fireEvent.click(within(card).getByRole('button', { name: 'Remove' }))
  await waitFor(() => expect(api.deleteCredential).toHaveBeenCalledWith('nexus'))
})

it('points back to the chat and the page after a save', async () => {
  vi.mocked(api.accountEntry).mockResolvedValue({ ...HERE, page: PAGE })
  renderAt('/accounts', <Screens />)
  const card = await screen.findByRole('region', { name: 'ecoinvent' })
  fireEvent.change(within(card).getByLabelText('Username'), { target: { value: 'carlos' } })
  fireEvent.change(within(card).getByLabelText('Password'), { target: { value: 'a secret' } })
  fireEvent.click(within(card).getByRole('button', { name: 'Save' }))
  expect(await within(card).findByText(/the chat/i)).toBeInTheDocument()
  expect(within(card).getByRole('link', { name: /page/i })).toHaveAttribute('href', PAGE)
})

it('shows the cards disabled off this computer', async () => {
  vi.mocked(api.accountEntry).mockResolvedValue(BRIDGED)
  renderAt('/accounts', <Screens />)
  await screen.findByRole('region', { name: 'Nexus' })
  expect(screen.getByText(TRAY)).toBeInTheDocument()
  const fields = screen.getAllByLabelText(/^(Username|Password|Token)$/)
  expect(fields.length).toBeGreaterThan(0)
  for (const field of fields) expect(field).toBeDisabled()
  const buttons = screen.getAllByRole('button')
  expect(buttons.length).toBeGreaterThan(0)
  for (const button of buttons) expect(button).toBeDisabled()
  expect(api.credentials).not.toHaveBeenCalled()
  expect(api.putCredential).not.toHaveBeenCalled()
})

it('reads the held kinds again on focus', async () => {
  vi.mocked(api.credentials).mockResolvedValueOnce({ held: ['nexus'] })
  renderAt('/accounts', <Screens />)
  const card = await screen.findByRole('region', { name: 'Nexus' })
  expect(await within(card).findByText(SAVED)).toBeInTheDocument()
  focusManager.setFocused(true)
  expect(await within(card).findByText(NOT_SAVED)).toBeInTheDocument()
})
