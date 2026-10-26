import type { DemandItem, ImpactArguments } from '@/api/types'

export interface ResultParams {
  method_id?: string
  impact_method?: string
  variants: string[]
  amount: number
  demand?: DemandItem[]
}

export function parseParams(search: string): ResultParams | null {
  const q = new URLSearchParams(search)
  const method_id = q.get('method_id') ?? undefined
  const impact_method = q.get('impact_method') ?? undefined
  if (!method_id && !impact_method) return null
  return {
    ...(method_id ? { method_id } : {}),
    ...(impact_method ? { impact_method } : {}),
    variants: (q.get('variants') ?? '').split(',').filter((v) => v.length > 0),
    amount: Number(q.get('amount') ?? '1'),
  }
}

export function callOf(search: string): string | null {
  return new URLSearchParams(search).get('call')
}

export function serializeParams(p: ResultParams): string {
  const q = new URLSearchParams()
  if (p.method_id) q.set('method_id', p.method_id)
  if (p.impact_method) q.set('impact_method', p.impact_method)
  if (p.variants.length > 0) q.set('variants', p.variants.join(','))
  if (p.amount !== 1) q.set('amount', String(p.amount))
  return `?${q.toString()}`
}

export function demandOf(p: ResultParams, root: string | null): DemandItem[] | undefined {
  if (p.demand !== undefined) return p.demand
  return p.amount !== 1 && root ? [{ ref: { kind: 'foreground', code: root }, amount: p.amount }] : undefined
}

export function toImpactArguments(p: ResultParams, root: string | null): ImpactArguments {
  const demand = demandOf(p, root)
  return {
    ...(p.method_id ? { method_id: p.method_id } : {}),
    ...(p.impact_method ? { impact_method: p.impact_method } : {}),
    variants: p.variants,
    ...(demand ? { demand } : {}),
  }
}
