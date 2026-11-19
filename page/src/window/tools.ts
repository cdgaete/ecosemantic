import { create } from 'zustand'
import { clearArea, type Bounds } from '@/editors/graph/layout'
import type { Offset } from '@/store/ui'
import { useClearance, type Box } from './clearance'

export const TOOLS_STEP = 24

interface ToolsPlace {
  live: Offset | null
  held: Offset | null
  setLive: (offset: Offset | null) => void
  setHeld: (offset: Offset | null) => void
}

/** Where the canvas tools are drawn away from the top centre: the offset of a drag under way, else the kept offset as this page holds it. */
export const useToolsPlace = create<ToolsPlace>((set) => ({
  live: null,
  held: null,
  setLive: (live) => set({ live }),
  setHeld: (held) => set((state) => (state.held?.x === held?.x && state.held?.y === held?.y ? {} : { held })),
}))

/**
 * The offset from the top centre the canvas tools settle at when they are wanted at one: inside the clear area,
 * held to its left, right and bottom, and null, the top centre again, when their top would be above it.
 */
export function settled(docked: Box, wanted: Offset, area: Bounds): Offset | null {
  const top = docked.top + wanted.y
  if (top < area.y) return null
  const width = docked.right - docked.left
  const height = docked.bottom - docked.top
  const left = Math.max(area.x, Math.min(docked.left + wanted.x, area.x + area.width - width))
  return { x: left - docked.left, y: Math.max(area.y, Math.min(top, area.y + area.height - height)) - docked.top }
}

/** The clear area of the page as its islands leave it now. */
export function clearNow(): Bounds {
  return clearArea({ width: window.innerWidth, height: window.innerHeight }, useClearance.getState().clearance)
}

/** The box an island is docked at: the box the layout gives it, which the offset it is drawn with does not move. */
export function dockedBox(island: HTMLElement): Box {
  const origin = island.offsetParent?.getBoundingClientRect() ?? { left: 0, top: 0 }
  const left = origin.left + island.offsetLeft
  const top = origin.top + island.offsetTop
  return { left, top, right: left + island.offsetWidth, bottom: top + island.offsetHeight }
}
