import type { Change, LogEntry } from '@/api/types'

export type DigestKey = 'processes' | 'exchanges' | 'edits' | 'deletions'
export type DigestFilter = DigestKey | 'failed'

export function counts(change: Change, key: DigestKey): boolean {
  if (key === 'processes') return change.op === 'add' && change.entity === 'process'
  if (key === 'exchanges') return change.op === 'add' && change.entity === 'exchange'
  if (key === 'edits') return change.op === 'update'
  return change.op === 'delete'
}

export function holds(entry: LogEntry, key: DigestKey): boolean {
  return entry.changes.some((change) => counts(change, key))
}

export function digestOf(entries: LogEntry[]): Record<DigestKey, number> {
  const changes = entries.flatMap((entry) => entry.changes)
  const of = (key: DigestKey) => changes.filter((change) => counts(change, key)).length
  return { processes: of('processes'), exchanges: of('exchanges'), edits: of('edits'), deletions: of('deletions') }
}
