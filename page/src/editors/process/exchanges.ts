import type { Exchange, Process, Side } from '@/api/types'

export function splitExchanges(process: Process, sides: Record<string, Side>): { inputs: Exchange[]; outputs: Exchange[]; unresolved: Exchange[] } {
  const inputs: Exchange[] = []
  const outputs: Exchange[] = []
  const unresolved: Exchange[] = []
  for (const exchange of process.exchanges) {
    if (exchange.type === 'production') outputs.push(exchange)
    else if (exchange.type === 'product') inputs.push(exchange)
    else if (exchange.input?.kind === 'elementary_flow') {
      const side = sides[exchange.input.id]
      if (side === 'input') inputs.push(exchange)
      else if (side === 'output') outputs.push(exchange)
      else unresolved.push(exchange)
    } else unresolved.push(exchange)
  }
  outputs.sort((a, b) => Number(b.type === 'production') - Number(a.type === 'production') || Number(a.amount === 0) - Number(b.amount === 0))
  inputs.sort((a, b) => Number(a.amount === 0) - Number(b.amount === 0))
  return { inputs, outputs, unresolved }
}
