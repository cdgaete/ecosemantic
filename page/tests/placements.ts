import type { Answer, Arrangement, CardGeometry, Exchange, Placement, ProductSystem, Route, SharedSupplier, StageRegions } from '@/api/types'

export interface StageAnswer {
  stages: StageRegions[]
  shared_suppliers: SharedSupplier[]
}

function isStageAnswer(given: ProductSystem | StageAnswer | string[]): given is StageAnswer {
  return !Array.isArray(given) && !('processes' in given)
}

function isCodes(given: ProductSystem | StageAnswer | string[]): given is string[] {
  return Array.isArray(given)
}

export const CARD: CardGeometry = { width: 300, header_height: 40, section_padding: 6, section_label: 18, row_height: 22 }

const FOLD = 6

const zeroLast = (a: Exchange, b: Exchange) => Number(a.amount === 0) - Number(b.amount === 0)

function arrowsOf(system: ProductSystem): Set<string> {
  const codes = new Set(system.processes.map((p) => p.code))
  return new Set(
    system.processes.flatMap((p) =>
      p.exchanges.filter((e) => (e.input?.kind === 'foreground' && codes.has(e.input.code)) || e.input?.kind === 'system').map((e) => e.id),
    ),
  )
}

export function placementsFor(...given: (ProductSystem | string[])[]): Placement[] {
  const expanded = given.find(isCodes) ?? []
  const systems = given.filter((item): item is ProductSystem => !isCodes(item))
  let y = 40
  return systems.flatMap((product) => {
    const arrows = arrowsOf(product)
    return product.processes.map((p) => {
      const inputs = p.exchanges.filter((e) => e.type === 'product').sort((a, b) => Number(!arrows.has(a.id)) - Number(!arrows.has(b.id)) || zeroLast(a, b))
      const outputs = [...p.exchanges.filter((e) => e.type === 'production'), ...p.exchanges.filter((e) => e.type === 'elementary').sort(zeroLast)]
      const kept = Math.max(FOLD, inputs.filter((e) => arrows.has(e.id)).length)
      const open = expanded.includes(p.code)
      const shown = open ? inputs.length : Math.min(inputs.length, kept)
      const shownOutputs = open ? outputs.length : Math.min(outputs.length, FOLD)
      const foldRows = Number(shown < inputs.length) + Number(shownOutputs < outputs.length)
      const section = 2 * CARD.section_padding + CARD.section_label
      const height = CARD.header_height + 2 * section + CARD.row_height * (shown + shownOutputs + foldRows)
      const at = y
      y += height + 40
      const first = CARD.header_height + section - CARD.section_padding + CARD.row_height / 2
      return {
        code: p.code,
        x: 0,
        y: at,
        width: CARD.width,
        height,
        depth: 0,
        shown_inputs: shown,
        shown_outputs: shownOutputs,
        folded_inputs: inputs.length - Math.min(inputs.length, kept),
        folded_outputs: outputs.length - Math.min(outputs.length, FOLD),
        held: false,
        placed_by: null,
        inputs: inputs.map((e, n) => ({ exchange_id: e.id, y: first + CARD.row_height * Math.min(n, shown) })),
        outputs: outputs.map((e) => e.id),
        output: CARD.header_height + section + CARD.row_height * (shown + Number(shown < inputs.length)) + section - CARD.section_padding + CARD.row_height / 2,
        activity: null,
        scaled: null,
      }
    })
  })
}

export function layoutAnswer(...given: (ProductSystem | StageAnswer | string[])[]): Answer<Arrangement> {
  const last = given[given.length - 1]
  const answer = last !== undefined && isStageAnswer(last) ? last : null
  const drawn = given.filter((item): item is ProductSystem | string[] => !isStageAnswer(item))
  return { value: { kind: 'arrangement', map: '', cards: placementsFor(...drawn), edges: [], troubles: [], score: 0, bounds: {}, scaling: null, stages: answer?.stages ?? [], shared_suppliers: answer?.shared_suppliers ?? [], card: CARD }, hint: null, view_url: null }
}

export function routesFor(...systems: ProductSystem[]): Route[] {
  const codes = new Set(systems.flatMap((system) => system.processes.map((p) => p.code)))
  return systems.flatMap((system) =>
    system.processes.flatMap((process) =>
      process.exchanges.flatMap((e) => {
        const input = e.input
        const provider =
          input?.kind === 'foreground' && codes.has(input.code)
            ? input.code
            : input?.kind === 'system'
              ? `system:${input.product_system_id}`
              : null
        if (provider === null) return []
        return [
          {
            provider,
            consumer: process.code,
            exchange_id: e.id,
            points: [] as [number, number][],
            label: { x: 0, y: 0, width: 0, height: 0, per_unit: `${e.amount} ${e.unit}`, scaled: null, formula: null },
          },
        ]
      }),
    ),
  )
}

export function routed(...systems: ProductSystem[]): Answer<Arrangement> {
  const answer = layoutAnswer(...systems)
  return { ...answer, value: { ...answer.value, edges: routesFor(...systems) } }
}
