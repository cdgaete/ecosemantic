import type { Call, DemandItem, ProductSystem } from '@/api/types'
import { heldVariant } from '@/window/useCanvasState'
import type { ResultParams } from './params'

/** The newest call that succeeded, which `/calculations` answers first, or undefined while none has. */
export function latestOf(calls: Call[]): Call | undefined {
  return calls.find((call) => call.outcome === 'ok')
}

export function variantsOf(call: Call): string[] {
  const variants = call.arguments.variants
  return Array.isArray(variants) ? variants.filter((v): v is string => typeof v === 'string') : []
}

export function paramsOfCall(call: Call): ResultParams {
  const { method_id, impact_method, demand } = call.arguments
  return {
    ...(typeof method_id === 'string' ? { method_id } : {}),
    ...(typeof impact_method === 'string' ? { impact_method } : {}),
    variants: variantsOf(call),
    amount: 1,
    ...(Array.isArray(demand) ? { demand: demand as unknown as DemandItem[] } : {}),
  }
}

export function ranMonteCarlo(call: Call): boolean {
  const config = call.arguments.monte_carlo
  return config !== undefined && config !== null
}

/** The params a calculation can be repeated with on `system`: the variants it holds kept, the ones it
 * does not in `missing`. */
export function heldParams(params: ResultParams, system: ProductSystem): { params: ResultParams; missing: string[] } {
  const kept: string[] = []
  const missing: string[] = []
  for (const name of params.variants) {
    if (heldVariant(system, name) === null) missing.push(name)
    else kept.push(name)
  }
  return { params: { ...params, variants: kept }, missing }
}

export function withoutDatabase(method: string, database: string): string {
  const prefix = `${database} > `
  return method.startsWith(prefix) ? method.slice(prefix.length) : method
}

export function methodOf(call: Call, database: string): string {
  const family = call.arguments.impact_method
  if (typeof family === 'string') return family
  const first = call.summary?.scores[0]?.method
  if (first !== undefined) return withoutDatabase(first, database)
  const named = call.arguments.method_id
  return typeof named === 'string' ? named : ''
}

export function targetOf(demand: DemandItem[] | null | undefined, system: ProductSystem | undefined): string | null {
  if (!demand || demand.length === 0) return null
  return demand
    .map((item) => {
      const ref = item.ref
      if (ref.kind !== 'foreground') return `${item.amount} of ${ref.id}`
      const process = system?.processes.find((p) => p.code === ref.code)
      return `${item.amount} ${process?.unit ?? ''} of ${process?.reference_product ?? ref.code}`
    })
    .join(', ')
}
