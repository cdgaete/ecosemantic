import { useUi } from '@/store/ui'

export const NARROWEST = 320
export const WIDEST_SHARE = 0.8
export const KEY_STEP = 24

/** The width a dragged panel takes: whole pixels, no narrower than 320 px and no wider than four fifths of the window. */
export function widthWithin(width: number, viewport: number): number {
  return Math.round(Math.max(NARROWEST, Math.min(width, viewport * WIDEST_SHARE)))
}

/** Holds the result drawer at a width a person gave it; null returns it to its own width. */
export function resizeResult(width: number | null): void {
  useUi.getState().setResultWidth(width === null ? null : widthWithin(width, window.innerWidth))
}
