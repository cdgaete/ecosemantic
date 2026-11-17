import type { LogEntry } from '@/api/types'

const PALETTE = 7
const HIGHLIGHT = 'rgb(var(--highlight))'

export const QUIET_AFTER = 5 * 60_000

export function colourOf(agent: string): string {
  let sum = 0
  for (const char of agent) sum = (sum * 31 + char.charCodeAt(0)) % 9973
  return `rgb(var(--chart-${(sum % PALETTE) + 1}))`
}

export function colourOfEntry(entry: LogEntry): string {
  return entry.actor.kind === 'agent' && entry.actor.id !== null ? colourOf(entry.actor.id) : HIGHLIGHT
}

export function quietSince(lastCallAt: string, now: number): boolean {
  return now - new Date(lastCallAt).getTime() > QUIET_AFTER
}

export function actorOf(entry: LogEntry): string {
  const { kind, id, name } = entry.actor
  if (id !== null) return `${kind} ${id}`
  if (name !== null) return `${kind} ${name}`
  return kind
}
