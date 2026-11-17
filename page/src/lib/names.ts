import { shortHash } from './format'

export function sharedNames(cards: { name: string }[]): Set<string> {
  const counts = new Map<string, number>()
  for (const card of cards) counts.set(card.name, (counts.get(card.name) ?? 0) + 1)
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name))
}

export function distinguishingId(card: { id: string; name: string }, shared: Set<string>): string | null {
  return shared.has(card.name) ? shortHash(card.id) : null
}
