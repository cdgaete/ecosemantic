import type { Exchange, Placement, Process } from '@/api/types'

export function rowsOf(process: Process, placement: Placement): { inputs: Exchange[]; outputs: Exchange[] } {
  const byId = new Map(process.exchanges.map((e) => [e.id, e]))
  return {
    inputs: placement.inputs.flatMap((port) => byId.get(port.exchange_id) ?? []),
    outputs: placement.outputs.flatMap((id) => byId.get(id) ?? []),
  }
}
