import type { Call, Json } from '@/api/types'

export function refKey(database: string | null, ref: string | null): string | null {
  return database !== null && ref !== null ? `${database}/${ref}` : null
}

function inputKey(input: Json | undefined): string | null {
  if (input === undefined || input === null || typeof input !== 'object' || Array.isArray(input)) return null
  const { database, id } = input
  return typeof database === 'string' && typeof id === 'string' ? refKey(database, id) : null
}

export function chosenRefs(trail: Call[], from: number): Set<string> {
  const chosen = new Set<string>()
  for (const call of trail.slice(from + 1)) {
    const key = call.effect === 'write' ? inputKey(call.arguments.input) : null
    if (key !== null) chosen.add(key)
  }
  return chosen
}
