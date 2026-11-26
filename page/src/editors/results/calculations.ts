import type { Call } from '@/api/types'
import { methodOf, variantsOf } from './recorded'
import type { Band } from './useBand'

export const NEW_CALCULATION = 'New calculation…'

/** What repeating `call` repeats: its method and the cases it scored, or the base values. */
export function runAgainLabel(call: Call, database: string): string {
  const variants = variantsOf(call)
  return `Run again: ${methodOf(call, database)} · ${variants.length > 0 ? variants.join(', ') : 'base values'}`
}

/** The address of the result the band's calculation computed, on the category and the case it shows. */
export function resultSearch(band: Band): string {
  const search = new URLSearchParams({ call: band.call.id })
  if (band.categories.length > 1 && band.chosen !== undefined) search.set('category', band.chosen.method_id)
  if (band.variant !== null) search.set('variant', band.variant)
  return `?${search.toString()}`
}
