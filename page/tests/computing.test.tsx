import { act, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useResult } from '@/editors/results/useResult'
import system from './fixtures/system.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: { ...original.api, system: vi.fn(async () => system), impact: vi.fn(() => new Promise(() => undefined)) },
  }
})

function Waiting() {
  return <p>{useResult().waiting}</p>
}

it('counts the seconds a calculation has taken while its result is on its way', async () => {
  vi.useFakeTimers()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/systems/${system.value.id}/results/impact?method_id=m_x`]}>
        <Routes>
          <Route path="systems/:id/results/*" element={<Waiting />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  // the system read and the calculation start on the first ticks
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100)
  })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4200)
  })
  expect(document.body.textContent).toContain('Calculating over the background database: 4 s')
  vi.useRealTimers()
})
