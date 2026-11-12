import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { ReactFlowProvider, useStoreApi } from '@xyflow/react'
import { useEffect } from 'react'
import { MemoryRouter } from 'react-router-dom'
import type { CardGeometry, Placement, ProductSystem } from '@/api/types'
import { buildGraph, hotFrom, type LinkedNodeType } from '@/editors/graph/build'
import { routed } from './placements'
import { LinkedNode } from '@/editors/graph/LinkedNode'
import { formatAmount } from '@/lib/format'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, systems: vi.fn(async () => systems) } }
})

const doc = system.value as ProductSystem
const part = (systems.value as { id: string; name: string }[]).find((s) => s.id !== doc.id)!

const placement: Placement = { code: 'system', x: 0, y: 0, width: 300, height: 74, depth: 0, shown_inputs: 0, held: false, inputs: [], outputs: [], output: 37, activity: null, scaled: null }
const card: CardGeometry = { width: 300, header_height: 40, section_padding: 6, section_label: 18, row_height: 22 }

function linking(): ProductSystem {
  const widget = doc.processes.find((p) => p.code === 'widget')!
  const frame = doc.processes.find((p) => p.code === 'frame')!
  const link = { kind: 'system' as const, product_system_id: part.id, at_hash: 'ab'.repeat(32), case: 'light' }
  return {
    ...doc,
    processes: [
      { ...widget, exchanges: [...widget.exchanges, { ...widget.exchanges[1], id: 'link-a', input: link }] },
      { ...frame, exchanges: [...frame.exchanges, { ...frame.exchanges[1], id: 'link-b', input: link }] },
    ],
  }
}

describe('a linked system on the canvas', () => {
  it('is one card with an arrow to each process consuming it', () => {
    const { nodes, edges } = buildGraph(linking(), routed(linking()).value, hotFrom(null), 'widget')
    const linked = nodes.filter((n) => n.type === 'linked')
    expect(linked.map((n) => n.id)).toEqual([`system:${part.id}`])
    const arrows = edges.filter((e) => e.source === `system:${part.id}`)
    expect(arrows.map((e) => e.target).sort()).toEqual(['frame', 'widget'])
  })

  it('draws the system icon, its name, its pin and its case, and opens the pinned version', async () => {
    const node = buildGraph(linking(), routed(linking()).value, hotFrom(null), 'widget').nodes.find((n) => n.type === 'linked') as LinkedNodeType
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReactFlowProvider>
            <LinkedNode {...({ id: node.id, data: { ...node.data, placement, card }, type: 'linked' } as unknown as Parameters<typeof LinkedNode>[0])} />
          </ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const name = await screen.findByText(part.name)
    expect((document.querySelector('[style*="height: 74px"]'))).not.toBeNull()
    expect((document.querySelector('.react-flow__handle') as HTMLElement).style.top).toBe('37px')
    expect(name.closest('a')?.getAttribute('href')).toContain(`/systems/${part.id}/versions/${'ab'.repeat(32)}`)
    expect(screen.getByText('ababab…abab')).toBeInTheDocument()
    expect(screen.getByText('case light')).toBeInTheDocument()
  })

  it('sizes the card, its header and its row from the geometry the layout hands it', async () => {
    const node = buildGraph(linking(), routed(linking()).value, hotFrom(null), 'widget').nodes.find((n) => n.type === 'linked') as LinkedNodeType
    const sized: CardGeometry = { width: 321, header_height: 44, section_padding: 8, section_label: 20, row_height: 26 }
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReactFlowProvider>
            <LinkedNode {...({ id: node.id, data: { ...node.data, placement, card: sized }, type: 'linked' } as unknown as Parameters<typeof LinkedNode>[0])} />
          </ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const name = await screen.findByText(part.name)
    const shell = document.querySelector('[style*="width: 321px"]') as HTMLElement
    expect(shell.style.height).toBe('74px')
    const header = name.closest('div') as HTMLElement
    expect(header.style.height).toBe('44px')
    const row = screen.getByText('ababab…abab').closest('div') as HTMLElement
    expect(row.style.height).toBe(`${sized.row_height + 2 * sized.section_padding}px`)
    expect(row.style.padding).toBe(`${sized.section_padding}px`)
  })

  it('turns to its name in large type below half zoom, as a process card does', async () => {
    const node = buildGraph(linking(), routed(linking()).value, hotFrom(null), 'widget').nodes.find((n) => n.type === 'linked') as LinkedNodeType
    function Zoomed() {
      const store = useStoreApi()
      useEffect(() => store.setState({ transform: [0, 0, 0.3] }), [store])
      return <LinkedNode {...({ id: node.id, data: { ...node.data, placement, card }, type: 'linked' } as unknown as Parameters<typeof LinkedNode>[0])} />
    }
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReactFlowProvider>
            <Zoomed />
          </ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const name = await screen.findByText(part.name)
    await waitFor(() => expect(name.closest('div')?.className).toContain('text-2xl'))
    expect(screen.queryByText('ababab…abab')).toBeNull()
  })

  it('shows the scaled output beside the pin in the scaled view, and nothing in the per-unit view', async () => {
    const node = buildGraph(linking(), routed(linking()).value, hotFrom(null), 'widget').nodes.find((n) => n.type === 'linked') as LinkedNodeType
    const drawn = (scaled: Record<string, number> | null) => (
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReactFlowProvider>
            <LinkedNode {...({ id: node.id, data: { ...node.data, placement: { ...placement, scaled }, card }, type: 'linked' } as unknown as Parameters<typeof LinkedNode>[0])} />
          </ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
    const view = render(drawn({ 'exchange-x': 1234.5 }))
    await screen.findByText(part.name)
    expect(screen.getByText(formatAmount(1234.5))).toBeInTheDocument()
    view.unmount()
    render(drawn(null))
    await screen.findByText(part.name)
    expect(screen.queryByText(formatAmount(1234.5))).toBeNull()
  })
})
