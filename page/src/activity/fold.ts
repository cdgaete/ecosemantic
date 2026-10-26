import type { Call } from '@/api/types'

export const FOLD_FROM = 3

export type Folded = { kind: 'call'; call: Call; at: number } | { kind: 'run'; tool: string; calls: Call[]; at: number }

function quiet(call: Call): boolean {
  return call.outcome === 'ok' && (call.summary === null || (call.summary.items.length === 0 && call.summary.scores.length === 0))
}

export function folded(calls: Call[]): Folded[] {
  const parts: Folded[] = []
  let at = 0
  while (at < calls.length) {
    let end = at
    if (quiet(calls[at])) while (end + 1 < calls.length && quiet(calls[end + 1]) && calls[end + 1].tool === calls[at].tool) end += 1
    const run = calls.slice(at, end + 1)
    if (run.length >= FOLD_FROM) parts.push({ kind: 'run', tool: calls[at].tool, calls: run, at })
    else run.forEach((call, offset) => parts.push({ kind: 'call', call, at: at + offset }))
    at = end + 1
  }
  return parts
}
