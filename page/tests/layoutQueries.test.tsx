import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { api } from '@/api/client'
import type { ProductSystem } from '@/api/types'
import { keys, useLayout, usePlaceCards, useReleaseCards } from '@/api/queries'
import system from './fixtures/system.json'
import { layoutAnswer } from './placements'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: { ...original.api, layout: vi.fn(), placeCards: vi.fn(), releaseCards: vi.fn() },
  }
})

const doc = system.value as ProductSystem
const ELSEWHERE = 'another-system'

function clientFor(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

function seeded(queryClient: QueryClient, ...presentations: [string, string | null, string[]][]): void {
  for (const [id, variant, expanded] of presentations) queryClient.setQueryData(keys.layout(id, variant, expanded), layoutAnswer(doc))
}

describe('the layout cache', () => {
  beforeEach(() => {
    vi.mocked(api.placeCards).mockReset()
    vi.mocked(api.releaseCards).mockReset()
    vi.mocked(api.layout).mockReset()
  })

  it('keeps the drawing a placement wrote and reads every other presentation of that system again', async () => {
    const queryClient = clientFor()
    const written = keys.layout(doc.id, null, [])
    const expanded = keys.layout(doc.id, null, ['frame', 'widget'])
    const variant = keys.layout(doc.id, 'heavy', [])
    const elsewhere = keys.layout(ELSEWHERE, null, [])
    seeded(queryClient, [doc.id, null, []], [doc.id, null, ['frame', 'widget']], [doc.id, 'heavy', []], [ELSEWHERE, null, []])
    const answer = layoutAnswer(doc)
    vi.mocked(api.placeCards).mockResolvedValue(answer)
    const { result } = renderHook(() => usePlaceCards(doc.id, null, []), { wrapper: wrapperFor(queryClient) })
    await act(async () => {
      await result.current.mutateAsync([{ code: 'widget', x: 40, y: 60 }])
    })
    expect(api.placeCards).toHaveBeenCalledWith(doc.id, [{ code: 'widget', x: 40, y: 60 }], null, [])
    expect(queryClient.getQueryData(written)).toEqual(answer)
    expect(queryClient.getQueryState(written)?.isInvalidated).toBe(false)
    expect(queryClient.getQueryState(expanded)?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(variant)?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(elsewhere)?.isInvalidated).toBe(false)
  })

  it('resets every presentation of the system under the rows the canvas shows, and none of another system', async () => {
    const queryClient = clientFor()
    const expanded = keys.layout(doc.id, null, ['frame', 'widget'])
    const plain = keys.layout(doc.id, null, [])
    const variant = keys.layout(doc.id, 'heavy', ['widget'])
    const elsewhere = keys.layout(ELSEWHERE, null, ['widget'])
    seeded(queryClient, [doc.id, null, ['frame', 'widget']], [doc.id, null, []], [doc.id, 'heavy', ['widget']], [ELSEWHERE, null, ['widget']])
    vi.mocked(api.releaseCards).mockResolvedValue(layoutAnswer(doc))
    const { result } = renderHook(() => useReleaseCards(doc.id, null, ['frame', 'widget']), { wrapper: wrapperFor(queryClient) })
    await act(async () => {
      await result.current.mutateAsync()
    })
    expect(api.releaseCards).toHaveBeenCalledWith(doc.id, null, ['frame', 'widget'])
    for (const key of [expanded, plain, variant]) expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(elsewhere)?.isInvalidated).toBe(false)
  })

  it('holds the previous drawing only while another presentation of the same system and variant reads', async () => {
    const queryClient = clientFor()
    seeded(queryClient, [doc.id, null, []])
    vi.mocked(api.layout).mockImplementation(() => new Promise(() => undefined))
    const initial: { systemId: string; variant: string | null; expanded: string[] } = { systemId: doc.id, variant: null, expanded: [] }
    const { result, rerender } = renderHook(
      ({ systemId, variant, expanded }: typeof initial) => useLayout(systemId, variant, expanded),
      { initialProps: initial, wrapper: wrapperFor(queryClient) },
    )
    await waitFor(() => expect(result.current.data).toEqual(layoutAnswer(doc)))
    rerender({ systemId: doc.id, variant: null, expanded: ['widget'] })
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(true))
    expect(result.current.data).toEqual(layoutAnswer(doc))
    rerender({ systemId: doc.id, variant: 'heavy', expanded: ['widget'] })
    await waitFor(() => expect(result.current.data).toBeUndefined())
    rerender({ systemId: ELSEWHERE, variant: null, expanded: ['widget'] })
    expect(result.current.data).toBeUndefined()
  })
})
