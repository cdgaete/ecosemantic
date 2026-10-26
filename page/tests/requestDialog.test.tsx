import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { RequestDialog } from '@/requests/RequestDialog'
import { useRequestDialog } from '@/requests/useRequestDialog'
import system from './fixtures/system.json'

const noHashSystem = { ...system, value: { ...system.value, hash: null } }

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, system: vi.fn(async () => noHashSystem) } }
})

describe('request dialog', () => {
  it('refuses to post when the stored product system carries no hash', async () => {
    useRequestDialog.setState({ target: { systemId: system.value.id } })
    renderAt('/', <RequestDialog />)
    await waitFor(() => expect(screen.getByText('The stored product system carries no hash yet.')).toBeInTheDocument())
    expect(screen.queryByLabelText('Message')).toBeNull()
  })

  it('closes from a visible Cancel, whatever the form can show', async () => {
    useRequestDialog.setState({ target: { systemId: system.value.id } })
    renderAt('/', <RequestDialog />)
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(useRequestDialog.getState().target).toBeNull())
  })
})
