import { shortHash } from './format'

export function movedSince(at: string | null | undefined, now: string | null | undefined): boolean {
  if (!at || !now) return false
  return at !== now
}

/** The line naming the version a calculation was recorded on and the one the page reads, or null
 * while both are the same. */
export function hashLine(recordedOn: string | null, currentOn: string | null): string | null {
  if (!movedSince(recordedOn, currentOn)) return null
  return `Recorded on ${shortHash(recordedOn)}; computed here on the current model, ${shortHash(currentOn)}.`
}
