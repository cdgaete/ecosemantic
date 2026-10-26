import { api, ApiError, rememberToken, withoutToken, withToken } from '@/api/client'
import system from './fixtures/system.json'
import notFound from './fixtures/error_not_found.json'
import run from './fixtures/run.json'
import installs from './fixtures/installs.json'

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

describe('client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends the token on every call once it is remembered', async () => {
    rememberToken('?token=abc')
    expect(withToken('/api/product-systems')).toBe('/api/product-systems?token=abc')
    expect(withToken('/api/databases/x/processes?query=steel')).toBe('/api/databases/x/processes?query=steel&token=abc')
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(respond(200, system))
    const read = await api.system(system.value.id)
    expect(read.value.name).toBe(system.value.name)
    expect(String(spy.mock.calls[0][0])).toContain('token=abc')
  })

  it('strips the token from a path and keeps the rest of its query', () => {
    expect(withoutToken('/systems/1/results/impact?impact_method=gwp&token=abc')).toBe('/systems/1/results/impact?impact_method=gwp')
    expect(withoutToken('/systems/1?token=abc')).toBe('/systems/1')
    expect(withoutToken('/systems/1')).toBe('/systems/1')
  })

  it('reads, lists, starts and cancels runs on their routes', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, run))
    await api.runs('s1')
    await api.run('r1')
    await api.startRun('s1', { impact_method: 'gwp', monte_carlo: { n_max: 400, scope: 'biosphere_only' } })
    await api.cancelRun('r1')
    const calls = spy.mock.calls.map(([url, init]) => [String(url).split('?')[0], init?.method ?? 'GET'])
    expect(calls).toEqual([
      ['/api/product-systems/s1/runs', 'GET'],
      ['/api/runs/r1', 'GET'],
      ['/api/product-systems/s1/runs', 'POST'],
      ['/api/runs/r1/cancel', 'POST'],
    ])
    expect(JSON.parse(String(spy.mock.calls[2][1]?.body))).toEqual({ impact_method: 'gwp', monte_carlo: { n_max: 400, scope: 'biosphere_only' } })
  })

  it('reads, places and releases the layout under the state named, and under the base without one', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, system))
    await api.layout('s1')
    await api.layout('s1', 'PPA solar 60%')
    await api.placeCards('s1', [{ code: 'a', x: 1, y: 2 }], 'PPA solar 60%')
    await api.placeCards('s1', [{ code: 'a', x: 1, y: 2 }])
    await api.releaseCards('s1', 'PPA solar 60%')
    const urls = spy.mock.calls.map(([url]) => withoutToken(String(url)))
    expect(urls).toEqual([
      '/api/product-systems/s1/layout',
      '/api/product-systems/s1/layout?variant=PPA+solar+60%25',
      '/api/product-systems/s1/layout',
      '/api/product-systems/s1/layout',
      '/api/product-systems/s1/layout?variant=PPA+solar+60%25',
    ])
    expect(JSON.parse(String(spy.mock.calls[2][1]?.body))).toEqual({ placements: [{ code: 'a', x: 1, y: 2 }], variant: 'PPA solar 60%' })
    expect(JSON.parse(String(spy.mock.calls[3][1]?.body))).toEqual({ placements: [{ code: 'a', x: 1, y: 2 }] })
  })

  it('marks an impact the person started, and every simulation start, for the recorder', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, { value: {} }))
    await api.impact('s1', { impact_method: 'IPCC 2021' })
    await api.impact('s1', { impact_method: 'IPCC 2021' }, true)
    await api.startRun('s1', { impact_method: 'IPCC 2021' })
    const asked = spy.mock.calls.map(([address]) => String(address))
    expect(asked[0]).not.toContain('started')
    expect(asked[1]).toContain('/impact?started=true')
    expect(asked[2]).toContain('/runs?started=true')
  })

  it('reads the agents, the calls, a trail and an open trail, and runs a call again', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, { value: [] }))
    await api.agents()
    await api.activity({ product_system_id: 's1', after: 'T0' })
    await api.trail('s1', 3)
    await api.openTrail('fixture-agent', 's1')
    await api.rerun('c1')
    const asked = spy.mock.calls.map(([address]) => String(address))
    expect(asked[0]).toContain('/api/agents')
    expect(asked[1]).toContain('/api/activity?product_system_id=s1&after=T0')
    expect(asked[2]).toContain('/api/product-systems/s1/log/3/trail')
    expect(asked[3]).toContain('/api/agents/fixture-agent/trail?product_system_id=s1')
    expect(asked[4]).toContain('/api/activity/c1/rerun')
    expect((spy.mock.calls[4][1] as RequestInit).method).toBe('POST')
    expect(api.allEventsUrl()).toContain('/api/events')
  })

  it('reads the sources, the installs, the credentials and the server, and posts and cancels an install', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, { value: [] }))
    await api.sources()
    await api.installs()
    await api.install('i1')
    await api.cancelInstall('i1')
    await api.postInstall({ source: 'uslci', version: '1.2026-09.0', system_model: null, replace: false, accept_terms: false, package: null, name: null, drop_unlinked: false })
    await api.credentials()
    await api.putCredential('nexus', { username: 'u', password: 'p', token: 't' })
    await api.deleteCredential('nexus')
    await api.server()
    expect(withoutToken(api.licenceUrl('i1'))).toBe('/api/installs/i1/licence')
    const calls = spy.mock.calls.map(([url, init]) => [withoutToken(String(url)), init?.method ?? 'GET'])
    expect(calls).toEqual([
      ['/api/sources', 'GET'],
      ['/api/installs', 'GET'],
      ['/api/installs/i1', 'GET'],
      ['/api/installs/i1/cancel', 'POST'],
      ['/api/installs', 'POST'],
      ['/api/credentials', 'GET'],
      ['/api/credentials/nexus', 'PUT'],
      ['/api/credentials/nexus', 'DELETE'],
      ['/api/server', 'GET'],
    ])
    expect(JSON.parse(String(spy.mock.calls[4][1]?.body))).toEqual({
      source: 'uslci',
      version: '1.2026-09.0',
      system_model: null,
      replace: false,
      accept_terms: false,
      package: null,
      name: null,
      drop_unlinked: false,
    })
    expect(JSON.parse(String(spy.mock.calls[6][1]?.body))).toEqual({ username: 'u', password: 'p', token: 't' })
  })

  it('uploads an openLCA zip as a form to its own route', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(200, installs))
    const form = new FormData()
    form.set('name', 'a database held')
    form.set('file', new File(['zip'], 'database.zip'))
    await api.uploadDatabase(form)
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit]
    expect(withoutToken(url)).toBe('/api/installs/openlca')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(form)
    expect(init.headers).toBeUndefined()
  })

  it('raises the envelope on an error', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => respond(404, notFound))
    await expect(api.system('missing')).rejects.toMatchObject({ status: 404, kind: 'not_found' })
    await expect(api.system('missing')).rejects.toBeInstanceOf(ApiError)
  })

  it('posts a calculation for its files and answers the zip', async () => {
    const fetched = vi.fn(async () => new Response(new Uint8Array([122, 105, 112]), { status: 200 }))
    vi.stubGlobal('fetch', fetched)
    const answered = await api.resultZip('s1', 'impact', { method_id: 'm1' })
    expect(answered.size).toBe(3)
    const [address, init] = fetched.mock.calls[0] as unknown as [string, RequestInit]
    expect(address).toContain('/api/product-systems/s1/impact.zip')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ method_id: 'm1' })
    vi.unstubAllGlobals()
  })
})
