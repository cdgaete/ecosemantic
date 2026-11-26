import { matchPath } from 'react-router-dom'
import { isActivityPath } from '@/lib/paths'
import { useUi, type InspectorMode } from '@/store/ui'
import { sheetOf, systemOf } from './sheets'
import { widthWithin } from './resize'
import { useMinWidth } from './useMinWidth'

export const NARROW_BELOW = 768

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

/**
 * Dismisses the inspector a blank canvas click or Escape leaves, where the window draws one: the address is under a
 * system and no sheet holds it. Anywhere else the mode stays as the person left it.
 */
export function dismissInspector(pathname: string): void {
  if (systemOf(pathname) === null || sheetOf(pathname) !== null) return
  const state = useUi.getState()
  if (!inspectorShown(state, narrowAt())) return
  closeInspector()
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

/** Draws the narrow sheet at its shorter height so the graph above it is larger, and returns it to the ordinary one. */
export function toggleSheetHeight(): void {
  const state = useUi.getState()
  state.setSheetShort(!state.sheetShort)
}

export function opensInspector(pathname: string): boolean {
  const id = matchPath('/systems/:id/*', pathname)?.params.id
  return id !== undefined && !isActivityPath(pathname, id)
}
