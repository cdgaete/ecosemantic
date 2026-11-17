import type { LogEntry } from '@/api/types'

export function entryAtHash(entries: LogEntry[], hash: string): LogEntry | undefined {
  return entries.find((entry) => entry.result_hash === hash)
}
