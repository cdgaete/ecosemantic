import { act, render, screen } from '@testing-library/react'
import { useLive } from '@/api/stream'
import { LiveStatus } from '@/window/LiveStatus'

afterEach(() => useLive.setState({ connection: 'closed', latest: {} }))

it('names each state of the connection and offers Reconnect once it is closed', () => {
  useLive.setState({ connection: 'connecting' })
  render(<LiveStatus />)
  expect(screen.getByText('Connecting…')).toBeInTheDocument()
  act(() => useLive.setState({ connection: 'open' }))
  expect(screen.getByText('Live')).toBeInTheDocument()
  act(() => useLive.setState({ connection: 'retrying' }))
  expect(screen.getByText('Reconnecting…')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reconnect' })).not.toBeInTheDocument()
  act(() => useLive.setState({ connection: 'closed' }))
  expect(screen.getByText('Disconnected')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reconnect' })).toBeInTheDocument()
})
