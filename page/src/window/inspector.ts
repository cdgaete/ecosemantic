import { matchPath } from 'react-router-dom'
import { isActivityPath } from '@/lib/paths'
import { useUi, type InspectorMode } from '@/store/ui'
import { useMinWidth } from './useMinWidth'

export const NARROW_BELOW = 768
export const NARROWEST = 320
export const WIDEST_SHARE = 0.8
export const KEY_STEP = 24

/** The width a dragged inspector takes: whole pixels, no narrower than 320 px and no wider than four fifths of the window. */
export function widthWithin(width: number, viewport: number): number {
  return Math.round(Math.max(NARROWEST, Math.min(width, viewport * WIDEST_SHARE)))
}

function narrowAt(): boolean {
  return !window.matchMedia(`(min-width: ${NARROW_BELOW}px)`).matches
}

export function inspectorShown(state: { inspector: InspectorMode; sheetOpen: boolean }, narrow: boolean): boolean {
  return narrow ? state.sheetOpen : state.inspector !== 'closed'
}

export function useInspectorShown(): boolean {
  const inspector = useUi((s) => s.inspector)
  const sheetOpen = useUi((s) => s.sheetOpen)
  return inspectorShown({ inspector, sheetOpen }, !useMinWidth(NARROW_BELOW))
}

export function openInspector(): void {
  const state = useUi.getState()
  if (narrowAt()) state.setSheetOpen(true)
  else if (state.inspector === 'closed') state.setInspector('open')
}

export function closeInspector(): void {
  const state = useUi.getState()
  if (narrowAt()) state.setSheetOpen(false)
  else state.setInspector('closed')
}

export function sheetShown(state: { sheetOpen: boolean }): boolean {
  return narrowAt() && state.sheetOpen
}

export function dismissSheet(): void {
  const state = useUi.getState()
  if (sheetShown(state)) state.setSheetOpen(false)
}

export function toggleInspector(): void {
  const state = useUi.getState()
  if (narrowAt()) state.setSheetOpen(!state.sheetOpen)
  else state.setInspector(state.inspector === 'closed' ? 'open' : 'closed')
}

/** Holds the inspector at a width a person gave it, out of the widened state; null returns it to its own width. */
export function resizeInspector(width: number | null): void {
  const state = useUi.getState()
  state.setInspectorWidth(width === null ? null : widthWithin(width, window.innerWidth))
  if (state.inspector === 'widened') state.setInspector('open')
}

export function toggleWidened(): void {
  const state = useUi.getState()
  state.setInspector(state.inspector === 'widened' ? 'open' : 'widened')
}

export function opensInspector(pathname: string): boolean {
  const id = matchPath('/systems/:id/*', pathname)?.params.id
  return id !== undefined && !isActivityPath(pathname, id)
}
