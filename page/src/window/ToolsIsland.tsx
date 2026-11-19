import { useLayoutEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { useClearance } from './clearance'
import { Slot } from './slots'
import { clearNow, dockedBox, settled, useToolsPlace } from './tools'

/** The island of the canvas tools: docked at the top centre, beside the name island, or drawn where a person dropped it over the graph. */
export function ToolsIsland() {
  const kept = useUi((s) => s.toolsOffset)
  const live = useToolsPlace((s) => s.live)
  const held = useToolsPlace((s) => s.held)
  const setHeld = useToolsPlace((s) => s.setHeld)
  const clearance = useClearance((s) => s.clearance)
  const island = useRef<HTMLDivElement>(null)
  const offset = live ?? held
  useLayoutEffect(() => {
    const drawn = island.current
    if (drawn === null) return
    setHeld(kept === null ? null : settled(dockedBox(drawn), kept, clearNow()))
  }, [kept, clearance, setHeld])
  return (
    <div
      ref={island}
      data-tools
      data-clear={offset === null ? 'top' : undefined}
      style={offset === null ? undefined : { transform: `translate(${offset.x}px, ${offset.y}px)` }}
      className={cn('col-start-2 row-start-1 min-w-0 justify-self-center self-start', offset !== null && 'z-10')}
    >
      <Slot name="tools" />
    </div>
  )
}
