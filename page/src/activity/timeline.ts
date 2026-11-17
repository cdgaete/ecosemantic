export const TIMELINE_CARD = 216

export function timelineFits(width: number): number {
  return Math.max(1, Math.floor((width + 8) / TIMELINE_CARD))
}
