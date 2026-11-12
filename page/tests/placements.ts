import type { Answer, Arrangement, CardGeometry, Exchange, Placement, ProductSystem, Route } from '@/api/types'

export const CARD: CardGeometry = { width: 300, header_height: 40, section_padding: 6, section_label: 18, row_height: 22 }

const FOLD = 6

const zeroLast = (a: Exchange, b: Exchange) => Number(a.amount === 0) - Number(b.amount === 0)

export function placementsFor(...systems: ProductSystem[]): Placement[] {
  let y = 40
  return systems.flatMap((product) =>
    product.processes.map((p) => {
      const inputs = p.exchanges.filter((e) => e.type === 'product').sort(zeroLast)
      const outputs = [...p.exchanges.filter((e) => e.type === 'production'), ...p.exchanges.filter((e) => e.type === 'elementary').sort(zeroLast)]
      const shown = Math.min(inputs.length, FOLD)
      const fold = inputs.length > FOLD ? 1 : 0
      const section = 2 * CARD.section_padding + CARD.section_label
      const height = CARD.header_height + 2 * section + CARD.row_height * (shown + fold + outputs.length)
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
        held: false,
        inputs: inputs.map((e, n) => ({ exchange_id: e.id, y: first + CARD.row_height * Math.min(n, shown) })),
        outputs: outputs.map((e) => e.id),
        output: CARD.header_height + section + CARD.row_height * (shown + fold) + section - CARD.section_padding + CARD.row_height / 2,
        activity: null,
        scaled: null,
      }
    }),
  )
}

export function layoutAnswer(...systems: ProductSystem[]): Answer<Arrangement> {
  return { value: { map: '', cards: placementsFor(...systems), edges: [], troubles: [], score: 0, bounds: {}, scaling: null, card: CARD }, hint: null, view_url: null }
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
