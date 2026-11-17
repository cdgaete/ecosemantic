import type { BackgroundExchange } from '@/api/types'

export function splitBackgroundExchanges(exchanges: BackgroundExchange[]): { inputs: BackgroundExchange[]; outputs: BackgroundExchange[] } {
  const inputs = exchanges.filter((e) => e.side === 'input')
  const outputs = exchanges.filter((e) => e.side === 'output')
  inputs.sort(referenceFirst)
  outputs.sort(referenceFirst)
  return { inputs, outputs }
}

function referenceFirst(a: BackgroundExchange, b: BackgroundExchange): number {
  return Number(b.reference) - Number(a.reference)
}
