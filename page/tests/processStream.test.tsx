import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { useProcessStream } from '@/api/processStream'
import { keys } from '@/api/queries'
import calls from './fixtures/calls.json'
import { FakeSource } from './fakeSource'

function Probe() {
  useProcessStream()
  return null
}

describe('process stream', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('refreshes the agents, the calls and the open trail of the agent that called, and closes', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const view = render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    expect(source.url).toContain('/api/events')
    const made = calls.value[0]
    act(() => source.emit('call', { kind: 'call', product_system_id: made.product_system_id, entry: null, request: null, run: null, call: made }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.agents })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['calls'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['calculations'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.openTrail(made.agent) })
    view.unmount()
    expect(source.readyState).toBe(2)
  })

  it('refreshes the systems list when a system is written or deleted anywhere', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 'a1', entry: null, request: null, run: null, call: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.systems })
    spy.mockClear()
    act(() => source.emit('deleted', { kind: 'deleted', product_system_id: 'a1', entry: null, request: null, run: null, call: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.systems })
  })
})
