import type { LogEntry, Process } from '@/api/types'

export function touches(entry: LogEntry, process: Process): boolean {
  const ids = new Set([process.id, ...process.exchanges.map((e) => e.id)])
  return entry.changes.some((change) => ids.has(change.id))
}
