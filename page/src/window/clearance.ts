import { useEffect, type RefObject } from 'react'
import { create } from 'zustand'

export type Side = 'left' | 'top' | 'right' | 'bottom'
export type Box = { left: number; top: number; right: number; bottom: number }
export type Clearance = Record<Side, number>

export const ISLAND_GAP = 12

const SIDES: Side[] = ['left', 'top', 'right', 'bottom']

export function clearanceOf(frame: Box, islands: { side: Side; box: Box }[], gap = ISLAND_GAP): Clearance {
  const clearance: Clearance = { left: gap, top: gap, right: gap, bottom: gap }
  for (const island of islands) {
    const { side, box } = island
    if (box.right - box.left === 0 && box.bottom - box.top === 0) continue
    const reach = {
      left: box.right - frame.left,
      top: box.bottom - frame.top,
      right: frame.right - box.left,
      bottom: frame.bottom - box.top,
    }[side]
    clearance[side] = Math.max(clearance[side], reach + gap)
  }
  return clearance
}

interface ClearanceState {
  clearance: Clearance
  setClearance: (clearance: Clearance) => void
}

export const useClearance = create<ClearanceState>((set) => ({
  clearance: { left: ISLAND_GAP, top: ISLAND_GAP, right: ISLAND_GAP, bottom: ISLAND_GAP },
  setClearance: (clearance) => set({ clearance }),
}))

function sideOf(element: HTMLElement): Side {
  const named = SIDES.find((side) => side === element.dataset.clear)
  if (named === undefined) throw new Error(`${String(element.dataset.clear)} names no side of the frame`)
  return named
}

/** Measures the islands of the frame into the clearance; a held frame measures nothing and keeps the clearance it had. */
export function useIslandClearance(frame: RefObject<HTMLElement | null>, layout: string, held = false): void {
  const setClearance = useClearance((s) => s.setClearance)
  useEffect(() => {
    const host = frame.current
    if (host === null || held) return
    const islands = Array.from(host.querySelectorAll<HTMLElement>('[data-clear]')).map((element) => ({ side: sideOf(element), element }))
    const measure = () =>
      setClearance(
        clearanceOf(
          host.getBoundingClientRect(),
          islands.map(({ side, element }) => ({ side, box: element.getBoundingClientRect() })),
        ),
      )
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(host)
    for (const island of islands) observer.observe(island.element)
    return () => observer.disconnect()
  }, [frame, layout, held, setClearance])
}
