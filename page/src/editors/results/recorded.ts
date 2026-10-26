import type { Call, DemandItem } from '@/api/types'
import type { ResultParams } from './params'

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
