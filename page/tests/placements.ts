import type { Answer, Arrangement, Exchange, Placement, ProductSystem } from '@/api/types'

const ROW = 22
const HEADER = 40
const SECTION = 30
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
      const height = HEADER + 2 * SECTION + ROW * (shown + fold + outputs.length)
      const at = y
      y += height + 40
      const first = HEADER + SECTION - 6 + ROW / 2
      return {
        code: p.code,
        x: 0,
        y: at,
        width: 300,
        height,
        depth: 0,
        shown_inputs: shown,
        row_height: ROW,
        held: false,
        inputs: inputs.map((e, n) => ({ exchange_id: e.id, y: first + ROW * Math.min(n, shown) })),
        outputs: outputs.map((e) => e.id),
        output: HEADER + SECTION + ROW * (shown + fold) + SECTION - 6 + ROW / 2,
        activity: null,
        scaled: null,
      }
    }),
  )
}

export function layoutAnswer(...systems: ProductSystem[]): Answer<Arrangement> {
  return { value: { map: '', cards: placementsFor(...systems), edges: [], troubles: [], score: 0, bounds: {}, scaling: null }, hint: null, view_url: null }
}
