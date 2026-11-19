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
  const byDatabase = new Map<string, NamedFlow[]>()
  for (const flow of named) {
    const held = byDatabase.get(flow.ref.database) ?? []
    held.push(flow)
    byDatabase.set(flow.ref.database, held)
  }
  const grouped = [...byDatabase.entries()]
  const answers = useQueries({
    queries: grouped.map(([database, refs]) => ({
      queryKey: keys.flows(database, refs.map(({ ref }) => ref.id)),
      queryFn: () => api.elementaryFlows(database, refs.map(({ ref }) => ref.id)),
      ...forever,
    })),
  })
  const flows: Record<string, FlowSide> = {}
  const errors: string[] = []
  answers.forEach((answer, i) => {
    const [database, refs] = grouped[i]
    if (answer.data) {
      const found = new Map(answer.data.value.map((flow) => [flow.ref.id, flow]))
      for (const { ref, name } of refs) {
        const flow = found.get(ref.id)
        if (!flow) {
          errors.push(`${name}: no flow '${ref.id}' in '${ref.database}'`)
          continue
        }
        flows[ref.id] = { side: flow.side, compartment: flow.compartment, flow_type: flow.flow_type }
      }
    }
    if (answer.error) errors.push(`${database}: ${answer.error.message}`)
  })
  return { flows, errors }
}

export function useFlowSides(exchanges: Exchange[]): FlowSides {
  return useElementaryFlows(elementaryRefs(exchanges.filter((exchange) => exchange.type === 'elementary'), (exchange) => exchange.name))
}
