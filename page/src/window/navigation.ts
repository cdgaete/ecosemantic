import { useUi } from '@/store/ui'

export const DOCKS_FROM = 1024

function docks(): boolean {
  return window.matchMedia(`(min-width: ${DOCKS_FROM}px)`).matches
}

export function openNavigation(): void {
  const state = useUi.getState()
  if (docks()) state.setNavDocked(true)
  else state.setNavOpen(true)
}

export function toggleNavigation(): void {
  const state = useUi.getState()
  if (docks()) state.setNavDocked(!state.navDocked)
  else state.setNavOpen(!state.navOpen)
}
