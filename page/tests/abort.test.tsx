import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, waitFor } from '@testing-library/react'
import { api } from '@/api/client'
import { keys, useLog } from '@/api/queries'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, log: vi.fn() } }
})

function Log({ id }: { id: string }) {
  useLog(id)
  return null
}

it('aborts a refresh the next one supersedes, so it frees its connection', async () => {
  const signals: (AbortSignal | undefined)[] = []
  vi.mocked(api.log).mockImplementation((_id: string, signal?: AbortSignal) => {
    signals.push(signal)
    // the first read answers; every refresh after it stays in flight
    return signals.length === 1 ? Promise.resolve({ value: [], hint: null, view_url: null }) : new Promise(() => undefined)
  })
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <Log id="s1" />
    </QueryClientProvider>,
  )
  await waitFor(() => expect(client.getQueryData(keys.log('s1'))).toBeDefined())
  await act(async () => {
    void client.invalidateQueries({ queryKey: keys.log('s1') })
  })
  await waitFor(() => expect(signals).toHaveLength(2))
  await act(async () => {
    void client.invalidateQueries({ queryKey: keys.log('s1') })
  })
  await waitFor(() => expect(signals).toHaveLength(3))
  expect(signals[1]?.aborted).toBe(true)
  expect(signals[2]?.aborted).toBe(false)
})
