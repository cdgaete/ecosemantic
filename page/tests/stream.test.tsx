import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { keys, useSystem } from '@/api/queries'
import { useLive, useSystemStream } from '@/api/stream'
import { useGo } from '@/lib/paths'
import log from './fixtures/log.json'
import run from './fixtures/run.json'
import system from './fixtures/system.json'
import { FakeSource } from './fakeSource'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, system: vi.fn(async () => system) } }
})

function Probe({ id }: { id: string }) {
  useSystemStream(id)
  const connection = useLive((s) => s.connection)
  return <span data-testid="state">{connection}</span>
}

describe('stream', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('invalidates the system on an entry and reports the connection open', async () => {
    const client = new QueryClient()
    client.setQueryData(keys.system('s1'), { value: { hash: 'old' }, hint: null, view_url: null, open_requests: 0 })
    const spy = vi.spyOn(client, 'invalidateQueries')
    const view = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    expect(source.url).toContain('/api/events')
    act(() => source.onopen?.())
    expect(view.getByTestId('state').textContent).toBe('open')
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.log('s1') })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
    expect(useLive.getState().latest.s1?.seq).toBe(log.value[0].seq)
  })

  it('invalidates the parameters of the system it follows on an entry', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: ['parameters', 's1'] })
  })

  it("writes a run event into that run's read and refreshes the list", () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    const moving = { ...run.value, status: 'running', open: true, result: null, progress: { iterations: 9, worst_rel_se: 0.3 } }
    act(() => source.emit('run', { kind: 'run', product_system_id: 's1', entry: null, request: null, run: moving }))
    expect(client.getQueryData(keys.run(moving.id))).toEqual({ value: moving, hint: null, view_url: null })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.runs('s1') })
  })

  it('reports retrying on an error and closed after the retries', () => {
    const client = new QueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.onerror?.())
    expect(view.getByTestId('state').textContent).toBe('retrying')
    act(() => {
      for (let i = 0; i < 30; i += 1) source.onerror?.()
    })
    expect(view.getByTestId('state').textContent).toBe('closed')
    expect(source.readyState).toBe(2)
  })

  it('reports closed at once when the browser closes the stream on an error', () => {
    const client = new QueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => {
      source.readyState = 2
      source.onerror?.()
    })
    expect(view.getByTestId('state').textContent).toBe('closed')
  })

  it('opens one EventSource for two editors of the same system and keeps it until the last unmounts', () => {
    const client = new QueryClient()
    const viewA = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const viewB = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    expect(FakeSource.instances).toHaveLength(1)
    const source = FakeSource.instances[0]
    viewA.unmount()
    expect(source.readyState).toBe(0)
    viewB.unmount()
    expect(source.readyState).toBe(2)
  })

  it('holds the stream open across the redraws its own events cause', async () => {
    function Consumer({ id }: { id: string }) {
      useSystem(id)
      const go = useGo()
      useSystemStream(id, go)
      return null
    }
    const client = new QueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Consumer id="s1" />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(FakeSource.instances).toHaveLength(1))
    const source = FakeSource.instances[0]
    act(() => source.onopen?.())
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null }))
    await waitFor(() => expect(useLive.getState().latest.s1?.seq).toBe(log.value[0].seq))
    const second = { ...log.value[0], seq: log.value[0].seq + 1 }
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: second, request: null }))
    await waitFor(() => expect(useLive.getState().latest.s1?.seq).toBe(second.seq))
    expect(FakeSource.instances).toHaveLength(1)
    expect(source.readyState).not.toBe(2)
    view.unmount()
  })

  it('keeps the connection open while every follower of a system remounts', async () => {
    const { useProcessStream } = await import('@/api/processStream')
    function Follower({ id }: { id: string }) {
      useSystemStream(id)
      return null
    }
    function Shell({ round }: { round: number }) {
      useProcessStream()
      const connection = useLive((s) => s.connection)
      return (
        <>
          <Follower key={`canvas-${round}`} id="s1" />
          <Follower key={`editor-${round}`} id="s1" />
          <span data-testid="state">{connection}</span>
        </>
      )
    }
    const client = new QueryClient()
    const view = render(
      <QueryClientProvider client={client}>
        <Shell round={1} />
      </QueryClientProvider>,
    )
    act(() => FakeSource.instances[0].onopen?.())
    expect(view.getByTestId('state').textContent).toBe('open')
    view.rerender(
      <QueryClientProvider client={client}>
        <Shell round={2} />
      </QueryClientProvider>,
    )
    expect(view.getByTestId('state').textContent).toBe('open')
    expect(FakeSource.instances).toHaveLength(1)
  })

  it('reads open again once a stream that errored opens', () => {
    const view = render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.onerror?.())
    expect(view.getByTestId('state').textContent).toBe('retrying')
    act(() => source.onopen?.())
    expect(view.getByTestId('state').textContent).toBe('open')
  })

  it('keeps the latest entry of each system apart', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe id="s1" />
        <Probe id="s2" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null }))
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's2', entry: { ...log.value[0], seq: 99 }, request: null }))
    expect(useLive.getState().latest.s1?.seq).toBe(log.value[0].seq)
    expect(useLive.getState().latest.s2?.seq).toBe(99)
  })
})

describe('one stream per tab', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('carries a system, the process and every other system on one EventSource, filtered by system', async () => {
    const { useProcessStream } = await import('@/api/processStream')
    function Tab() {
      useSystemStream('s1')
      useProcessStream()
      return null
    }
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const view = render(
      <QueryClientProvider client={client}>
        <Tab />
      </QueryClientProvider>,
    )
    expect(FakeSource.instances).toHaveLength(1)
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's2', entry: log.value[0], request: null, run: null, call: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.systems })
    expect(spy).not.toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null, run: null, call: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    act(() => source.emit('call', { kind: 'call', product_system_id: null, entry: null, request: null, run: null, call: { agent: 'a1' } }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.agents })
    view.unmount()
    expect(source.readyState).toBe(2)
  })
})

describe('validation follows a linked system', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it("refetches this system's validation on an entry of a system it links", () => {
    const client = new QueryClient()
    const doc = system.value as { processes: { exchanges: unknown[] }[] }
    const linking = {
      ...doc,
      processes: doc.processes.map((p, i) =>
        i === 0 ? { ...p, exchanges: [...p.exchanges, { id: 'l1', type: 'product', name: 'part', amount: 1, unit: 'unit', input: { kind: 'system', product_system_id: 'part', at_hash: 'a', case: null }, formula: null, comment: null, uncertainty: null }] } : p,
      ),
    }
    client.setQueryData(keys.system('s1'), { value: linking, hint: null, view_url: null, open_requests: 0 })
    const spy = vi.spyOn(client, 'invalidateQueries')
    render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 'elsewhere', entry: log.value[0], request: null, run: null, call: null }))
    expect(spy).not.toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 'part', entry: log.value[0], request: null, run: null, call: null }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
  })
})
