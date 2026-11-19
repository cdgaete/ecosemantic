import { GripVertical } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { cn } from '@/lib/utils'
import { useUi, type Offset } from '@/store/ui'
import type { Box } from './clearance'
import { clearNow, dockedBox, settled, TOOLS_STEP, useToolsPlace } from './tools'

const STEPS: Record<string, Offset> = {
  ArrowLeft: { x: -TOOLS_STEP, y: 0 },
  ArrowRight: { x: TOOLS_STEP, y: 0 },
  ArrowUp: { x: 0, y: -TOOLS_STEP },
  ArrowDown: { x: 0, y: TOOLS_STEP },
}

interface Grabbed {
  pointer: Offset
  from: Offset
  docked: Box
}

/** The handle of the canvas tools: dragging it moves their island over the graph, the arrow keys move it in steps, and a double click or Home returns it to the top centre. */
export function ToolsGrip() {
  const handle = useRef<HTMLButtonElement>(null)
  const grabbed = useRef<Grabbed | null>(null)
  const [dragging, setDragging] = useState(false)
  useEffect(() => {
    if (!dragging) return
    const move = (event: PointerEvent) => {
      const start = grabbed.current
      if (start === null) return
      useToolsPlace.getState().setLive({ x: start.from.x + event.clientX - start.pointer.x, y: start.from.y + event.clientY - start.pointer.y })
    }
    const drop = () => {
      const start = grabbed.current
      const reached = useToolsPlace.getState().live
      grabbed.current = null
      setDragging(false)
      useToolsPlace.getState().setLive(null)
      if (start !== null && reached !== null) useUi.getState().setToolsOffset(settled(start.docked, reached, clearNow()))
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', drop)
    window.addEventListener('pointercancel', drop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', drop)
      window.removeEventListener('pointercancel', drop)
    }
  }, [dragging])
  const place = (): { from: Offset; docked: Box } | null => {
    const island = handle.current?.closest<HTMLElement>('[data-tools]') ?? null
    if (island === null) return null
    return { from: useToolsPlace.getState().held ?? { x: 0, y: 0 }, docked: dockedBox(island) }
  }
  const grab = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const at = place()
    if (at === null) return
    event.preventDefault()
    grabbed.current = { pointer: { x: event.clientX, y: event.clientY }, ...at }
    setDragging(true)
  }
  const step = (event: KeyboardEvent<HTMLButtonElement>) => {
    const by = STEPS[event.key]
    const at = place()
    if (at === null || (by === undefined && event.key !== 'Home')) return
    event.preventDefault()
    useUi.getState().setToolsOffset(by === undefined ? null : settled(at.docked, { x: at.from.x + by.x, y: at.from.y + by.y }, clearNow()))
  }
  return (
    <button
      ref={handle}
      type="button"
      aria-label="Move the canvas tools"
      title="Drag to move; double-click to return to the top centre"
      className={cn(
        'flex h-7 w-4 shrink-0 touch-none items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring',
        dragging ? 'cursor-grabbing' : 'cursor-grab',
      )}
      onPointerDown={grab}
      onDoubleClick={() => useUi.getState().setToolsOffset(null)}
      onKeyDown={step}
    >
      <GripVertical className="size-3.5" />
    </button>
  )
}
