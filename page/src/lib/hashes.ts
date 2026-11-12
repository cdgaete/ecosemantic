export function movedSince(at: string | null | undefined, now: string | null | undefined): boolean {
  if (!at || !now) return false
  return at !== now
}
