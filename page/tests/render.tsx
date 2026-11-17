import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Slot, SlotsProvider } from '@/window/slots'

export function renderAt(path: string, ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <TooltipProvider>{ui}</TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export function renderInSlots(path: string, ui: ReactNode) {
  return renderAt(
    path,
    <SlotsProvider>
      <Slot name="tools" />
      <Slot name="view" />
      <Slot name="minimap" />
      <Slot name="notice" />
      {ui}
    </SlotsProvider>,
  )
}
