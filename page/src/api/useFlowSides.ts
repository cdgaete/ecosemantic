import { useQueries } from '@tanstack/react-query'
import { api } from './client'
import { forever, keys } from './queries'
import type { ElementaryFlowRef, Exchange, ExchangeInput, FlowType, Side } from './types'

export interface FlowSide {
  side: Side
  compartment: string
  flow_type: FlowType
}

export interface FlowSides {
  sides: Record<string, Side>
  flows: Record<string, FlowSide>
  errors: string[]
}

export interface NamedFlow {
  ref: ElementaryFlowRef
  name: string
}

export function elementaryRefs<T extends { input: ExchangeInput | null }>(rows: T[], name: (row: T) => string): NamedFlow[] {
  const named = new Map<string, NamedFlow>()
  for (const row of rows) {
    const input = row.input
    if (input?.kind !== 'elementary_flow') continue
    const key = `${input.database}:${input.id}`
    if (!named.has(key)) named.set(key, { ref: input, name: name(row) })
  }
  return [...named.values()]
}

export function useElementaryFlows(named: NamedFlow[]): FlowSides {
  const answers = useQueries({
    queries: named.map(({ ref }) => ({ queryKey: keys.flow(ref.database, ref.id), queryFn: () => api.elementaryFlow(ref.database, ref.id), ...forever })),
  })
  const sides: Record<string, Side> = {}
  const flows: Record<string, FlowSide> = {}
  const errors: string[] = []
  answers.forEach((answer, i) => {
    const { ref, name } = named[i]
    if (answer.data) {
      sides[ref.id] = answer.data.value.side
      flows[ref.id] = { side: answer.data.value.side, compartment: answer.data.value.compartment, flow_type: answer.data.value.flow_type }
    }
    if (answer.error) errors.push(`${name}: ${answer.error.message}`)
  })
  return { sides, flows, errors }
}

export function useFlowSides(exchanges: Exchange[]): FlowSides {
  return useElementaryFlows(elementaryRefs(exchanges.filter((exchange) => exchange.type === 'elementary'), (exchange) => exchange.name))
}
