import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { api } from '@/api/client'
import { useSystemStream } from '@/api/stream'
import { LiveStatus } from '@/window/LiveStatus'
import { FakeSource } from './fakeSource'

function Page() {
  useSystemStream('s1')
  return <LiveStatus />
}

describe('a page waiting on a connection slot', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('says so, and how many streams this browser holds, once a fetch outlives the deadline', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Page />
      </QueryClientProvider>,
    )
    void api.systems()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.queryByText(/Waiting on a connection slot/)).toBeNull()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByText(/Waiting on a connection slot: this browser holds 1 event stream/)).toBeInTheDocument()
  })
})
