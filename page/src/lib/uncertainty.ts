import type { Uncertainty } from '@/api/types'
import { formatAmount } from './format'

function amount(v: number | boolean): string {
  return formatAmount(Number(v)).replace('-', '−')
}

function withUnit(text: string, unit: string): string {
  return unit === '' ? text : `${text} ${unit}`
}

function bounds(u: Uncertainty, unit: string): string {
  const low = typeof u.params.minimum === 'number' ? u.params.minimum : null
  const high = typeof u.params.maximum === 'number' ? u.params.maximum : null
  if (low !== null && high !== null) return `, bounded ${withUnit(`${amount(low)} to ${amount(high)}`, unit)}`
  if (low !== null) return `, at least ${withUnit(amount(low), unit)}`
  if (high !== null) return `, at most ${withUnit(amount(high), unit)}`
  return ''
}

export function describeUncertainty(u: Uncertainty | null, unit: string): string {
  if (u === null) return 'none'
  const p = u.params
  if (u.type === 'uniform') return withUnit(`uniform, ${amount(p.minimum)} to ${amount(p.maximum)}`, unit)
  if (u.type === 'triangular') return `triangular, ${withUnit(`${amount(p.minimum)} to ${amount(p.maximum)}`, unit)}, mode ${amount(p.loc)}`
  if (u.type === 'normal') return `normal, sd ${withUnit(amount(p.scale), unit)}${bounds(u, unit)}`
  return `lognormal, GSD² ${formatAmount(Math.exp(2 * Number(p.scale)))}${bounds(u, unit)}`
}
