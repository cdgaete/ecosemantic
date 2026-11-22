import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { renderAt } from './render'
import { App } from '@/App'
import { api } from '@/api/client'
import type { Answer, ImpactResult } from '@/api/types'
import { useUi } from '@/store/ui'
import { useChooseCase } from '@/window/useChooseCase'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import validation from './fixtures/validation.json'
import recordedImpact from './fixtures/impact.json'

const impact = recordedImpact as Answer<ImpactResult>
const id = system.value.id

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      validation: vi.fn(async () => validation),
      impact: vi.fn(async () => impact),
    },
  }
})

function ShowSearch() {
  const location = useLocation()
  return <output data-testid="search">{location.search}</output>
}

function wrapperAt(address: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[address]}>
          {children}
          <ShowSearch />
        </MemoryRouter>
      </QueryClientProvider>
    )
  }
}

const search = () => screen.getByTestId('search').textContent ?? ''
const bodies = () => vi.mocked(api.impact).mock.calls.map(([, body]) => body)

beforeEach(() => {
  cleanup()
  useUi.setState({ canvasVariant: null, canvasSystemId: null })
  vi.mocked(api.impact).mockClear()
})

it('an address case becomes the canvas state', async () => {
  renderAt(`/systems/${id}/results/impact?method_id=m_bff077f3bd&variant=heavy`, <App router={false} />)
  await waitFor(() => expect(useUi.getState().canvasVariant).toBe('heavy'))
  await waitFor(() => expect(bodies()).toContainEqual(expect.objectContaining({ method_id: 'm_bff077f3bd', variants: ['heavy'] })))
})

it('choosing a state on a result writes the address', () => {
  const { result } = renderHook(() => useChooseCase(id), {
    wrapper: wrapperAt(`/systems/${id}/results/impact?method_id=m_bff077f3bd&variant=heavy`),
  })
  act(() => result.current('lighter'))
  expect(useUi.getState().canvasVariant).toBe('lighter')
  expect(search()).toContain('variant=lighter')
  act(() => result.current(null))
  expect(useUi.getState().canvasVariant).toBeNull()
  expect(search()).not.toContain('variant')
})

it('choosing a state on the graph leaves the address', () => {
  const { result } = renderHook(() => useChooseCase(id), { wrapper: wrapperAt(`/systems/${id}?tab=activity`) })
  act(() => result.current('heavy'))
  expect(useUi.getState().canvasVariant).toBe('heavy')
  expect(search()).toBe('?tab=activity')
})

it('an address case the system lacks is named and not read', async () => {
  renderAt(`/systems/${id}/results/impact?method_id=m_bff077f3bd&variant=nowhere`, <App router={false} />)
  expect(await screen.findByText('Case nowhere is not in this system; the pages read the base values.')).toBeInTheDocument()
  await waitFor(() => expect(bodies()).toContainEqual(expect.objectContaining({ method_id: 'm_bff077f3bd' })))
  for (const body of bodies()) expect(body.variants ?? []).not.toContain('nowhere')
})
