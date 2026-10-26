import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { createElement } from 'react'
import { connectEvents } from '@/api/connect'
import { keys } from '@/api/queries'
import { openStreams, useHeldStream, useLive } from '@/api/stream'
import installs from './fixtures/installs.json'
import { FakeSharedWorker } from './fakeSharedWorker'
import { FakeSource } from './fakeSource'

describe('one stream per browser', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
    vi.stubGlobal('SharedWorker', FakeSharedWorker)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('holds one connection between three tabs and hands every event to each', () => {
    const tabs = [connectEvents('/api/events'), connectEvents('/api/events'), connectEvents('/api/events')]
    expect(FakeSource.instances).toHaveLength(1)
    const heard: string[] = []
    tabs.forEach((tab, i) => tab.addEventListener('entry', (e) => heard.push(`${i}:${(e as MessageEvent).data as string}`)))
    FakeSource.instances[0].emit('entry', { seq: 7 })
    expect(heard).toEqual(['0:{"seq":7}', '1:{"seq":7}', '2:{"seq":7}'])
    tabs[0].close()
    tabs[1].close()
    expect(FakeSource.instances[0].readyState).toBe(0)
    tabs[2].close()
    expect(FakeSource.instances[0].readyState).toBe(2)
  })

  it('tells a tab that joins an open stream that it is open', () => {
    FakeSharedWorker.connect = null
    const first = connectEvents('/api/events')
    const opened: string[] = []
    first.onopen = () => opened.push('first')
    const source = FakeSource.instances[0]
    source.readyState = 1
    source.onopen?.()
    const late = connectEvents('/api/events')
    late.onopen = () => opened.push('late')
    expect(opened).toEqual(['first'])
    expect(late.readyState).toBe(1)
    first.close()
    late.close()
  })

  it('drops a tab hidden for good, and takes it back when the page is restored', () => {
    FakeSharedWorker.connect = null
    const tab = connectEvents('/api/events')
    const first = FakeSource.instances[0]
    window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: false }))
    expect(first.readyState).toBe(2)
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(FakeSource.instances).toHaveLength(2)
    const heard: string[] = []
    tab.addEventListener('entry', (e) => heard.push((e as MessageEvent).data as string))
    FakeSource.instances[1].emit('entry', { seq: 3 })
    expect(heard).toEqual(['{"seq":3}'])
    tab.close()
  })

  it('opens a new stream for a tab asking for one the browser closed for good', () => {
    FakeSharedWorker.connect = null
    const first = connectEvents('/api/events')
    FakeSource.instances[0].readyState = 2
    const second = connectEvents('/api/events')
    expect(FakeSource.instances).toHaveLength(2)
    const heard: string[] = []
    first.addEventListener('entry', (e) => heard.push(`first:${(e as MessageEvent).data as string}`))
    second.addEventListener('entry', (e) => heard.push(`second:${(e as MessageEvent).data as string}`))
    FakeSource.instances[1].emit('entry', { seq: 4 })
    expect(heard).toEqual(['first:{"seq":4}', 'second:{"seq":4}'])
    first.close()
    second.close()
    expect(FakeSource.instances[1].readyState).toBe(2)
  })
})


describe('the page holds its stream', () => {
  beforeEach(() => {
    FakeSource.instances = []
    FakeSharedWorker.connect = null
    vi.stubGlobal('EventSource', FakeSource)
    vi.stubGlobal('SharedWorker', FakeSharedWorker)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('test_the_shared_stream_stays_open_with_nothing_followed', () => {
    const client = new QueryClient()
    function Held() {
      useHeldStream()
      return null
    }
    const view = render(createElement(QueryClientProvider, { client }, createElement(Held)))
    expect(FakeSource.instances).toHaveLength(1)
    expect(openStreams()).toBe(1)
    const source = FakeSource.instances[0]
    act(() => {
      for (let i = 0; i < 20; i += 1) source.onerror?.()
    })
    expect(useLive.getState().connection).toBe('retrying')
    expect(source.readyState).toBe(0)
    act(() => {
      for (let i = 0; i < 11; i += 1) source.onerror?.()
    })
    expect(useLive.getState().connection).toBe('closed')
    expect(source.readyState).toBe(2)
    view.unmount()
    expect(openStreams()).toBe(0)
  })

  it('refreshes the installs, and the databases once an install is done', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    function Held() {
      useHeldStream()
      return null
    }
    const view = render(createElement(QueryClientProvider, { client }, createElement(Held)))
    const source = FakeSource.instances[0]
    act(() => source.emit('install', { kind: 'install', product_system_id: null, install: { ...installs.value[0], status: 'running', open: true } }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.installs })
    expect(spy).not.toHaveBeenCalledWith({ queryKey: keys.databases })
    act(() => source.emit('install', { kind: 'install', product_system_id: null, install: { ...installs.value[0], status: 'done', open: false } }))
    expect(spy).toHaveBeenCalledWith({ queryKey: keys.databases })
    view.unmount()
  })
})
