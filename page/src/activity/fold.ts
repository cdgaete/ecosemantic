import type { Call } from '@/api/types'

export type Folded = { kind: 'write'; call: Call; at: number } | { kind: 'reads'; calls: Call[]; at: number }

function reads(call: Call): boolean {
  return call.effect === 'read' || call.effect === 'compute'
}

export function folded(calls: Call[]): Folded[] {
  const parts: Folded[] = []
  let at = 0
  while (at < calls.length) {
    if (!reads(calls[at])) {
      parts.push({ kind: 'write', call: calls[at], at })
      at += 1
      continue
    }
    let end = at
    while (end + 1 < calls.length && reads(calls[end + 1])) end += 1
    parts.push({ kind: 'reads', calls: calls.slice(at, end + 1), at })
    at = end + 1
  }
  return parts
}

interface Tally {
  tool: string
  calls: number
  failed: number
}

function tallies(calls: Call[]): Tally[] {
  const counted: Tally[] = []
  for (const call of calls) {
    let tally = counted.find((one) => one.tool === call.tool)
    if (tally === undefined) {
      tally = { tool: call.tool, calls: 0, failed: 0 }
      counted.push(tally)
    }
    tally.calls += 1
    if (call.outcome === 'error') tally.failed += 1
  }
  return counted
}

export function foldedLine(calls: Call[]): string {
  return tallies(calls)
    .map(({ tool, calls: times, failed }) => {
      const named = times > 1 ? `${tool} ×${times}` : tool
      return failed > 0 ? `${named}, ${failed} failed` : named
    })
    .join(' · ')
}
