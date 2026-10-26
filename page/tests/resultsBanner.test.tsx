import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from '@/api/client'
import type { Answer, ImpactResult, SystemRead } from '@/api/types'
import { ResultsEditor } from '@/editors/results/ResultsEditor'
import system from './fixtures/system.json'
import validation from './fixtures/validation.json'
import recordedImpact from './fixtures/impact.json'
import byProcess from './fixtures/contributions_process.json'

const impact = recordedImpact as Answer<ImpactResult>
const changed = { ...system, value: { ...system.value, hash: 'a-different-hash' } }

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      system: vi.fn(async () => changed),
      validation: vi.fn(async () => validation),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => byProcess),
    },
  }
})

// A minimal EventSource double that records its listeners so a test can trigger them,
// the same shape as tests/stream.test.tsx's.
class FakeSource {
  static readonly CLOSED = 2
  static instances: FakeSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 0
  constructor(url: string) {
    this.url = url
    FakeSource.instances.push(this)
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  emit(type: string, data: unknown) {
    this.listeners[type]?.forEach((fn) => fn(new MessageEvent(type, { data: JSON.stringify(data) })))
  }
  close() {
    this.readyState = 2
  }
}

beforeEach(() => {
  vi.mocked(api.impact).mockClear()
  vi.mocked(api.contributions).mockClear()
  FakeSource.instances = []
  vi.stubGlobal('EventSource', FakeSource)
})
afterEach(() => vi.unstubAllGlobals())

it('shows the model-changed banner on a stream entry and only recalculates when asked', async () => {
  vi.mocked(api.system).mockResolvedValueOnce(system as SystemRead)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const address = `/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[address]}>
        <Routes>
          <Route path="systems/:id/results/*" element={<ResultsEditor />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(1))

  const source = FakeSource.instances[0]
  act(() => source.emit('entry', { kind: 'entry', product_system_id: system.value.id, entry: null, request: null }))
  await waitFor(() => expect(screen.getByText('The model changed since this result was computed.')).toBeInTheDocument())
  expect(api.impact).toHaveBeenCalledTimes(1)

  fireEvent.click(screen.getByText('Recalculate'))
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(2))
})

it('computes no page an entry has made stale and asks for a recalculation instead', async () => {
  vi.mocked(api.system).mockResolvedValueOnce(system as SystemRead)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const address = `/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[address]}>
        <Routes>
          <Route path="systems/:id/results/*" element={<ResultsEditor />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(1))
  const source = FakeSource.instances.at(-1)!
  act(() => source.emit('entry', { kind: 'entry', product_system_id: system.value.id, entry: null, request: null }))
  await waitFor(() => expect(screen.getByText('The model changed since this result was computed.')).toBeInTheDocument())

  fireEvent.click(screen.getByRole('link', { name: 'Process results' }))
  await waitFor(() => expect(screen.getByText('Process contributions')).toBeInTheDocument())
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(api.contributions).not.toHaveBeenCalled()
  expect(screen.getByText('Recalculate to compute this page for the current model.')).toBeInTheDocument()
  expect(screen.queryByText(/Calculating over the background database/)).toBeNull()
})

function openImpact() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const address = `/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[address]}>
        <Routes>
          <Route path="systems/:id/results/*" element={<ResultsEditor />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

it('names each loop holding a credit, in the base and in each variant, above the results', async () => {
  vi.mocked(api.system).mockResolvedValueOnce(system as SystemRead)
  const variant = { name: 'used', scores: impact.value.scores, deltas: [0], credit_loops: [['frame', 'part', 'widget']], linked_credit_loops: [], treatments_run_backwards: [], uncertainty: null, paired_deltas: null }
  vi.mocked(api.impact).mockResolvedValueOnce({ ...impact, value: { ...impact.value, credit_loops: [['frame', 'widget']], variants: [variant] } })
  openImpact()
  await waitFor(() => expect(screen.getByText('The loop through frame, widget holds a credit; whether it delivers what it makes is not checked.')).toBeInTheDocument())
  expect(screen.getByText('In used, the loop through frame, part, widget holds a credit; whether it delivers what it makes is not checked.')).toBeInTheDocument()
})

it('names each exchange that runs a treatment backwards, in the base and in each variant, above the results', async () => {
  vi.mocked(api.system).mockResolvedValueOnce(system as SystemRead)
  const variant = { name: 'used', scores: impact.value.scores, deltas: [0], credit_loops: [], linked_credit_loops: [], treatments_run_backwards: ['widget · steel at 1'], uncertainty: null, paired_deltas: null }
  vi.mocked(api.impact).mockResolvedValueOnce({ ...impact, value: { ...impact.value, treatments_run_backwards: ['widget · steel at 0.5'], variants: [variant] } })
  openImpact()
  await waitFor(() => expect(screen.getByText('widget · steel at 0.5 sends a positive amount to a treatment, which runs it backwards and counts its emissions as credits; waste goes to a treatment as a negative input.')).toBeInTheDocument())
  expect(screen.getByText('In used, widget · steel at 1 sends a positive amount to a treatment, which runs it backwards and counts its emissions as credits; waste goes to a treatment as a negative input.')).toBeInTheDocument()
})

it('says nothing of loops when none holds a credit', async () => {
  vi.mocked(api.system).mockResolvedValueOnce(system as SystemRead)
  openImpact()
  await waitFor(() => expect(api.impact).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.getAllByText(impact.value.scores[0].method.impact_category).length).toBeGreaterThan(0))
  expect(screen.queryByText(/holds a credit/)).not.toBeInTheDocument()
})
