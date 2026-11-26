import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { KEY_STEP, NARROWEST, WIDEST_SHARE, widthWithin } from './resize'

export interface ResizeEdgeProps {
  label: string
  panel: () => HTMLElement | null
  width: number | null
  onDrag: (width: number | null) => void
  onDrop: (width: number) => void
  onReset: () => void
}

/**
 * The left border of a panel beside the canvas: dragged to a width the caller holds, stepped from the keyboard,
 * and double-clicked back to the panel's own width.
 */
export function ResizeEdge({ label, panel, width, onDrag, onDrop, onReset }: ResizeEdgeProps) {
  const [dragging, setDragging] = useState(false)
  const dragged = useRef<number | null>(null)
  useEffect(() => {
    if (!dragging) return
    const move = (event: PointerEvent) => {
      const held = panel()
      if (held === null) return
      dragged.current = widthWithin(held.getBoundingClientRect().right - event.clientX, window.innerWidth)
      onDrag(dragged.current)
    }
    const drop = () => {
      setDragging(false)
      onDrag(null)
      if (dragged.current !== null) onDrop(dragged.current)
      dragged.current = null
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', drop)
    window.addEventListener('pointercancel', drop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', drop)
      window.removeEventListener('pointercancel', drop)
    }
  }, [dragging, panel, onDrag, onDrop])
  const step = (event: KeyboardEvent<HTMLDivElement>) => {
    const by = event.key === 'ArrowLeft' ? KEY_STEP : event.key === 'ArrowRight' ? -KEY_STEP : 0
    const held = panel()
    if (by === 0 || held === null) return
    event.preventDefault()
    onDrop(held.getBoundingClientRect().width + by)
  }
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={NARROWEST}
      aria-valuemax={Math.round(window.innerWidth * WIDEST_SHARE)}
      aria-valuenow={width ?? undefined}
      tabIndex={0}
      title="Drag to resize; double-click to return to the usual width"
      className={cn(
        'absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none transition-colors duration-150 hover:bg-foreground/10 focus-visible:bg-ring/50 focus-visible:outline-none',
        dragging && 'bg-ring/50',
      )}
      onPointerDown={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDoubleClick={onReset}
      onKeyDown={step}
    />
  )
}
