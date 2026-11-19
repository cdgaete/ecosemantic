import type { Entity, ProductSystem } from '@/api/types'
import { shortHash } from './format'

export function sharedNames(cards: { name: string }[]): Set<string> {
  const counts = new Map<string, number>()
  for (const card of cards) counts.set(card.name, (counts.get(card.name) ?? 0) + 1)
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name))
}

export function distinguishingId(card: { id: string; name: string }, shared: Set<string>): string | null {
  return shared.has(card.name) ? shortHash(card.id) : null
}

export function entityKind(entity: Entity): string {
  return entity.replaceAll('_', ' ')
}

export function entityName(system: ProductSystem, entity: Entity, id: string): string {
  if (entity === 'product_system') return system.name
  if (entity === 'process') return system.processes.find((process) => process.code === id || process.id === id)?.name ?? id
  if (entity === 'exchange') {
    for (const process of system.processes) {
      const exchange = process.exchanges.find((e) => e.id === id)
      if (exchange) return `${exchange.name} on ${process.name}`
    }
  }
  return id
}
