import { screen, waitFor } from '@testing-library/react'
import { api } from '@/api/client'
import type { ServerInfo } from '@/api/types'
import { TopBar } from '@/window/TopBar'
import server from './fixtures/server.json'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, server: vi.fn(async () => server) } }
})

it('names the connected chatbot', async () => {
  renderAt('/', <TopBar menu={null} />)
  expect(await screen.findByText(`Connected: ${server.client.name}`)).toBeInTheDocument()
})

it('says nothing when no chatbot introduced itself', async () => {
  vi.mocked(api.server).mockResolvedValue({ ...server, client: null } as unknown as ServerInfo)
  renderAt('/', <TopBar menu={null} />)
  await waitFor(() => expect(api.server).toHaveBeenCalledTimes(2))
  expect(screen.queryByText(/Connected:/)).not.toBeInTheDocument()
})

it('shows the logo before the name', () => {
  renderAt('/', <TopBar menu={null} />)
  const logo = screen.getByRole('img', { name: 'EcoSemantic' })
  const name = screen.getByText('EcoSemantic')
  expect(logo.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})
