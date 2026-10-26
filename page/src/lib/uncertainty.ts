import type { Uncertainty } from '@/api/types'
import { formatAmount } from './format'

const ORDER = ['minimum', 'loc', 'scale', 'maximum', 'negative']

export function describeUncertainty(u: Uncertainty | null): string {
  if (u === null) return 'none'
  const parts = ORDER.filter((k) => k in u.params).map((k) => {
    const v = u.params[k]
    return `${k} ${typeof v === 'boolean' ? String(v) : formatAmount(v).replace('-', '−')}`
  })
  return `${u.type} · ${parts.join(', ')}`
}
