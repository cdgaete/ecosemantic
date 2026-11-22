import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Answer, Arrangement, ContributionResult, ProductSystem, Region, SharedSupplier, StagePart } from '@/api/types'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { useUi } from '@/store/ui'
import { Slot, SlotsProvider } from '@/window/slots'
import { layoutAnswer, placementsFor, type StageAnswer } from './placements'
import contributions from './fixtures/contributions_stage.json'
import system from './fixtures/system.json'

const doc = system.value as ProductSystem
const recorded = contributions as unknown as Answer<ContributionResult>
const TOTAL = 4.158

const { rendered } = vi.hoisted(() => ({ rendered: { layout: null as unknown as Answer<Arrangement> } }))

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      layout: vi.fn(async () => rendered.layout),
      placeCards: vi.fn(async () => rendered.layout),
    },
  }
})

const PLACEMENTS = placementsFor(doc)

function around(code: string): Region {
  const spot = PLACEMENTS.find((p) => p.code === code)!
  const pad = 24
  return { x: spot.x - pad, y: spot.y - pad, width: spot.width + 2 * pad, height: spot.height + 2 * pad }
}

const ONE_EACH: StageAnswer = {
  stages: [
    { stage: 'assembly', codes: ['widget'], regions: [around('widget')] },
    { stage: 'materials', codes: ['frame'], regions: [around('frame')] },
  ],
  shared_suppliers: [],
}

function part(stage: string, score: number, fraction: number): StagePart {
  return {
    stage,
    score,
    fraction,
    processes: [{ ref: { kind: 'foreground', code: stage === 'assembly' ? 'widget' : 'frame' }, name: stage, location: 'GLO', score, fraction, direct: 0, inputs: [] }],
  }
}

function splitOf(stages: StagePart[]): ContributionResult {
  return { ...recorded.value, by: 'stage', total: { ...recorded.value.total, value: TOTAL, unit: 'kg CO2-Eq' }, stages }
}

const SPLIT = splitOf([part('assembly', 2.49, 0.5988), part('materials', 1.668, 0.4012)])
const CREDIT = splitOf([part('assembly', -0.01, -0.006), part('materials', 1.668, 0.4012)])

function renderGraph(split?: ContributionResult) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TooltipProvider>
          <SlotsProvider>
            <Slot name="tools" />
            <Slot name="view" />
            <Slot name="minimap" />
            <Slot name="notice" />
            <ModelGraph system={doc} latest={null} split={split} />
          </SlotsProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function boxes(container: HTMLElement, stage: string): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(`[data-stage="${stage}"]`))
}

function tabOf(container: HTMLElement, stage: string): HTMLElement {
  return container.querySelector<HTMLElement>(`[data-stage="${stage}"] [data-stage-tab]`)!
}

describe('the stage boxes', () => {
  beforeEach(() => useUi.setState({ canvasSystemId: doc.id, canvasVariant: null }))

  it('each stage is a box behind its cards', async () => {
    rendered.layout = layoutAnswer(doc, ONE_EACH)
    const { container } = renderGraph()
    const drawn = await waitFor(() => {
      const found = Array.from(container.querySelectorAll<HTMLElement>('[data-stage]'))
      expect(found).toHaveLength(2)
      return found
    })
    expect(within(drawn[0]!).getByText(/^assembly/)).toBeInTheDocument()
    expect(within(drawn[1]!).getByText(/^materials/)).toBeInTheDocument()
    const cards = Array.from(container.querySelectorAll<HTMLElement>('.react-flow__node:not([data-id^="stage:"])'))
    expect(cards.length).toBeGreaterThan(0)
    const lowest = Math.min(...cards.map((card) => Number(card.style.zIndex)))
    for (const box of drawn) expect(Number(box.closest<HTMLElement>('.react-flow__node')!.style.zIndex)).toBeLessThan(lowest)
    const region = ONE_EACH.stages[0]!.regions[0]!
    expect(drawn[0]!.closest<HTMLElement>('.react-flow__node')!.style.transform.replace(/\s+/g, '')).toBe(`translate(${region.x}px,${region.y}px)`)
    expect(drawn[0]!.style.width).toBe(`${region.width}px`)
    expect(drawn[0]!.style.height).toBe(`${region.height}px`)
  })

  it("a box labels its signed share in its stage's colour", async () => {
    rendered.layout = layoutAnswer(doc, ONE_EACH)
    const first = renderGraph(SPLIT)
    await waitFor(() => expect(tabOf(first.container, 'assembly').textContent).toBe('assembly · 59.9 % · 2.49 kg CO2-Eq'))
    expect(tabOf(first.container, 'assembly').style.backgroundColor).toContain('--stage-1')
    first.unmount()
    const credit = renderGraph(CREDIT)
    await waitFor(() => expect(tabOf(credit.container, 'assembly').textContent).toContain('-0.6 %'))
    expect(tabOf(credit.container, 'assembly').style.backgroundColor).toContain('--stage-1')
  })

  it('two regions of one stage are tethered', async () => {
    rendered.layout = layoutAnswer(doc, {
      stages: [
        { stage: 'assembly', codes: ['widget'], regions: [around('widget'), { x: -400, y: 0, width: 348, height: 240 }] },
        { stage: 'materials', codes: ['frame'], regions: [around('frame')] },
      ],
      shared_suppliers: [],
    })
    const { container } = renderGraph()
    await waitFor(() => expect(boxes(container, 'assembly')).toHaveLength(2))
    await waitFor(() => expect(container.querySelectorAll('.react-flow__edge-tether')).toHaveLength(1))
  })

  it('a shared supplier says what it feeds', async () => {
    const shared: SharedSupplier[] = [{ code: 'frame', processes: 2, stages: 2 }]
    rendered.layout = layoutAnswer(doc, { stages: ONE_EACH.stages, shared_suppliers: shared })
    const { container } = renderGraph()
    const card = await waitFor(() => {
      const found = container.querySelector<HTMLElement>('.react-flow__node[data-id="frame"]')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(within(card).getByText('supplies 2 processes in 2 stages')).toBeInTheDocument()
  })
})
