import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { keys, useSystem } from '@/api/queries'
import { gathered, useLive, useSystemStream } from '@/api/stream'
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
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.log('s1') })
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
    expect(useLive.getState().latest.s1?.seq).toBe(log.value[0].seq)
  })

  it('invalidates the parameters of the system it follows on an entry', async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null }))
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).toHaveBeenCalledWith({ queryKey: ['parameters', 's1'] })
  })

  it("writes a run event into that run's read and refreshes the list", async () => {
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
    await act(() => new Promise(requestAnimationFrame))
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
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.systems })
    expect(spy).not.toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null, run: null, call: null }))
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.system('s1') })
    act(() => source.emit('call', { kind: 'call', product_system_id: null, entry: null, request: null, run: null, call: { agent: 'a1' } }))
    await act(() => new Promise(requestAnimationFrame))
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

  it("refetches this system's validation on an entry of a system it links", async () => {
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
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).not.toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
    act(() => source.emit('entry', { kind: 'entry', product_system_id: 'part', entry: log.value[0], request: null, run: null, call: null }))
    await act(() => new Promise(requestAnimationFrame))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.validation('s1') })
  })
})

describe('events that arrive together', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('gathers the keys in first-seen order, dropping a repeat and a key a gathered key covers', () => {
    expect(gathered([['system', 's1'], ['systems', 'home'], ['systems'], ['system', 's1'], ['calls', 's1', null], ['calls']])).toEqual([
      ['system', 's1'],
      ['systems'],
      ['calls'],
    ])
  })

  it('refetches each key once for an entry, a layout and a call that arrive together', async () => {
    const { useProcessStream } = await import('@/api/processStream')
    function Process() {
      useProcessStream()
      return null
    }
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const view = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
        <Process />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => {
      source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null, run: null, call: null })
      source.emit('layout', { kind: 'layout', product_system_id: 's1', entry: null, request: null, run: null, call: null })
      source.emit('call', { kind: 'call', product_system_id: 's1', entry: null, request: null, run: null, call: { agent: 'a1' } })
    })
    expect(spy).not.toHaveBeenCalled()
    await act(() => new Promise(requestAnimationFrame))
    const asked = spy.mock.calls.map(([filter]) => JSON.stringify(filter?.queryKey)).sort()
    const once = [
      keys.system('s1'),
      keys.log('s1'),
      keys.validation('s1'),
      keys.anchors('s1'),
      keys.layouts('s1'),
      ['parameters', 's1'],
      keys.systems,
      keys.agents,
      ['calls'],
      ['calculations'],
      keys.openTrail('a1'),
    ]
      .map((queryKey) => JSON.stringify(queryKey))
      .sort()
    expect(asked).toEqual(once)
    view.unmount()
  })

  it('holds a thousand entries for one system to one key each at the frame', async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const hashed = vi.spyOn(JSON, 'stringify')
    const view = render(
      <QueryClientProvider client={client}>
        <Probe id="s1" />
      </QueryClientProvider>,
    )
    const source = FakeSource.instances[0]
    act(() => {
      for (let i = 0; i < 1000; i += 1) source.emit('entry', { kind: 'entry', product_system_id: 's1', entry: log.value[0], request: null, run: null, call: null })
    })
    expect(spy).not.toHaveBeenCalled()
    hashed.mockClear()
    await act(() => new Promise(requestAnimationFrame))
    const gatheredWork = hashed.mock.calls.length
    const asked = spy.mock.calls.map(([filter]) => JSON.stringify(filter?.queryKey)).sort()
    const once = [keys.system('s1'), keys.log('s1'), keys.validation('s1'), keys.anchors('s1'), keys.layouts('s1'), ['parameters', 's1']]
      .map((queryKey) => JSON.stringify(queryKey))
      .sort()
    expect(asked).toEqual(once)
    // A key named a thousand times is held once, so the frame hashes the six distinct keys and not the backlog.
    expect(gatheredWork).toBeLessThan(1000)
    hashed.mockRestore()
    view.unmount()
  })
})
