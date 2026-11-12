import { waitFor } from '@testing-library/react'
import { App } from '@/App'
import { FakeSource } from './fakeSource'
import { renderAt } from './render'

const none = { value: [], hint: null, view_url: null }

describe('held stream', () => {
  beforeEach(() => {
    FakeSource.instances = []
    vi.stubGlobal('EventSource', FakeSource)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(none), { headers: { 'content-type': 'application/json' } })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('opens at an address carrying the token the page was opened with', async () => {
    renderAt('/?token=secret', <App router={false} />)
    await waitFor(() => expect(FakeSource.instances.length).toBeGreaterThan(0))
    expect(FakeSource.instances.map((source) => source.url)).toEqual(['/api/events?token=secret'])
  })
})
