import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useUi, type EditorTab } from '@/store/ui'
import { Breadcrumb } from '@/window/Breadcrumb'

const systemId = 'd2dece81'
const system: EditorTab = { id: `system:${systemId}`, kind: 'system', title: 'Cátodo de cobre', path: `/systems/${systemId}/parameters` }
const smelter: EditorTab = { id: `process:${systemId}:smelter`, kind: 'process', title: 'Fundición', path: `/systems/${systemId}/processes/smelter/io` }

function crumbs(trail: EditorTab[]): string[] {
  useUi.setState({ canvasSystemId: systemId, trail })
  const view = render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Breadcrumb />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const names = within(screen.getByRole('navigation', { name: 'Breadcrumb' }))
    .getAllByRole('link')
    .map((link) => link.textContent ?? '')
  view.unmount()
  return names
}

afterEach(() => useUi.setState({ canvasSystemId: null, trail: [] }))

it('ends at the system when the system is what Details shows, after a process was open', () => {
  expect(crumbs([smelter, system]).slice(2)).toEqual([])
})

it('names what was opened after the system', () => {
  expect(crumbs([system, smelter]).slice(2)).toEqual(['Fundición'])
})

it('names what was opened while the system itself never was', () => {
  expect(crumbs([smelter]).slice(2)).toEqual(['Fundición'])
})
