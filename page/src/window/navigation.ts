import { useUi } from '@/store/ui'

export function openNavigation(): void {
  useUi.getState().setNavOpen(true)
}

export function closeNavigation(): void {
  useUi.getState().setNavOpen(false)
}

export function toggleNavigation(): void {
  const state = useUi.getState()
  state.setNavOpen(!state.navOpen)
}
