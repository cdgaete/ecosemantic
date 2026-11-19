import { useEffect } from 'react'
import { useUi } from '@/store/ui'
import { dismissSheet, sheetShown, toggleInspector } from './inspector'
import { closeNavigation, toggleNavigation } from './navigation'

export interface Shortcut {
  id: string
  keys: string
  label: string
  run: () => void
}

export const CANVAS_EVENT = 'ecosemantic:canvas'
export type CanvasCommand = 'fit' | 'focus' | 'reorganise' | { show: string }

export function runCanvas(command: CanvasCommand): void {
  window.dispatchEvent(new CustomEvent<CanvasCommand>(CANVAS_EVENT, { detail: command }))
}

function canvas(command: CanvasCommand): () => void {
  return () => runCanvas(command)
}

export const LEAVE_EVENT = 'ecosemantic:leave'

function dismiss(): void {
  const state = useUi.getState()
  if (state.navOpen) closeNavigation()
  else if (sheetShown(state)) dismissSheet()
  else if (state.toolsOpen) state.setToolsOpen(false)
  else window.dispatchEvent(new Event(LEAVE_EVENT))
}

export const SHORTCUTS: Shortcut[] = [
  { id: 'palette', keys: 'Ctrl+K', label: 'Go to anything, or run a command', run: () => useUi.getState().setPaletteOpen(true) },
  { id: 'navigation', keys: 'Ctrl+B', label: 'Show or hide the navigation', run: toggleNavigation },
  { id: 'inspector', keys: 'Ctrl+Alt+B', label: 'Show or hide the inspector', run: toggleInspector },
  { id: 'fit', keys: '1', label: 'Fit the graph to the canvas', run: canvas('fit') },
  { id: 'focus', keys: 'F', label: 'Centre the reference process', run: canvas('focus') },
  { id: 'reorganise', keys: 'R', label: 'Reorganise the graph', run: canvas('reorganise') },
  { id: 'dismiss', keys: 'Escape', label: 'Close the navigation, the sheet or the canvas tools, or leave the explorer', run: dismiss },
]

export function keysOf(id: string): string {
  const found = SHORTCUTS.find((shortcut) => shortcut.id === id)
  if (!found) throw new Error(`no shortcut ${id}`)
  return found.keys
}

function pressed(event: KeyboardEvent, keys: string): boolean {
  const parts = keys.toLowerCase().split('+')
  const key = parts[parts.length - 1]
  return (
    event.key.toLowerCase() === key &&
    (event.ctrlKey || event.metaKey) === parts.includes('ctrl') &&
    event.altKey === parts.includes('alt') &&
    event.shiftKey === parts.includes('shift')
  )
}

function fieldOf(target: EventTarget | null): HTMLElement | null {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) ? target : null
}

export function useShortcuts(): void {
  useEffect(() => {
    const listen = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return
      const field = fieldOf(event.target)
      if (field !== null) {
        if (event.key === 'Escape') field.blur()
        return
      }
      const found = SHORTCUTS.find((shortcut) => pressed(event, shortcut.keys))
      if (!found) return
      event.preventDefault()
      found.run()
    }
    window.addEventListener('keydown', listen)
    return () => window.removeEventListener('keydown', listen)
  }, [])
}
