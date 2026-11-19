import { Maximize2, Minimize2, PanelRightClose, PanelRightOpen, Pin } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Outlet } from 'react-router-dom'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { IconButton } from './IconButton'
import { closeInspector, KEY_STEP, NARROW_BELOW, NARROWEST, openInspector, resizeInspector, toggleWidened, useInspectorShown, WIDEST_SHARE, widthWithin } from './inspector'
import { PinChips } from './PinChips'
import { useMinWidth } from './useMinWidth'

const VIEW = 'rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'
const CURRENT = 'bg-background text-foreground shadow-sm'

function ResizeEdge({ panel, width, onDrag }: { panel: () => HTMLElement | null; width: number | null; onDrag: (width: number | null) => void }) {
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
      if (dragged.current !== null) resizeInspector(dragged.current)
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
  }, [dragging, panel, onDrag])
  const step = (event: KeyboardEvent<HTMLDivElement>) => {
    const by = event.key === 'ArrowLeft' ? KEY_STEP : event.key === 'ArrowRight' ? -KEY_STEP : 0
    const held = panel()
    if (by === 0 || held === null) return
    event.preventDefault()
    resizeInspector(held.getBoundingClientRect().width + by)
  }
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the inspector"
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
      onDoubleClick={() => resizeInspector(null)}
      onKeyDown={step}
    />
  )
}

export function Inspector() {
  const shown = useInspectorShown()
  const narrow = !useMinWidth(NARROW_BELOW)
  const systemId = useUi((s) => s.canvasSystemId)
  const details = useUi((s) => s.details)
  const lastDetails = useUi((s) => s.lastDetails)
  const pinned = useUi((s) => s.pinned)
  const widened = useUi((s) => s.inspector === 'widened')
  const kept = useUi((s) => s.inspectorWidth)
  const pin = useUi((s) => s.pin)
  const panel = useRef<HTMLElement>(null)
  const held = useRef(() => panel.current)
  const [dragged, setDragged] = useState<number | null>(null)
  const isPinned = details !== null && pinned.some((p) => p.id === details.id)
  if (!shown) {
    return narrow ? null : (
      <div data-clear="right" className="col-start-3 row-start-2 self-start justify-self-end rounded-xl border bg-chrome/95 p-1 shadow-lg">
        <IconButton label="Show the inspector" shortcut="inspector" side="left" onClick={openInspector}>
          <PanelRightOpen />
        </IconButton>
      </div>
    )
  }
  const width = narrow ? null : (dragged ?? (widened ? null : kept))
  return (
    <aside
      ref={panel}
      aria-label="Inspector"
      data-clear={narrow ? undefined : 'right'}
      style={narrow ? undefined : { maxWidth: `${WIDEST_SHARE * 100}vw`, ...(width === null ? {} : { width: `${width}px` }) }}
      className={cn(
        'relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-background shadow-lg',
        narrow
          ? cn('col-span-2 col-start-1', widened ? 'row-span-2 row-start-1 self-stretch' : 'row-span-1 row-start-2 h-[62%] self-end')
          : cn('col-start-3 row-span-2 row-start-2 justify-self-end', widened ? 'w-[min(840px,60vw)]' : 'w-[360px] min-[1280px]:w-[400px]'),
      )}
    >
      {narrow ? null : <ResizeEdge panel={held.current} width={width} onDrag={setDragged} />}
      <div className="flex items-center gap-1 border-b bg-chrome p-1">
        {systemId === null ? null : (
          <>
            <AppLink to={paths.system(systemId)} aria-current={details === null ? 'page' : undefined} className={cn(VIEW, details === null && CURRENT)}>
              Activity
            </AppLink>
            <AppLink to={details?.path ?? lastDetails?.path ?? paths.systemPage(systemId, 'general')} aria-current={details !== null ? 'page' : undefined} className={cn(VIEW, details !== null && CURRENT)}>
              Details
            </AppLink>
          </>
        )}
        <span className="min-w-0 flex-1 truncate px-2.5 text-xs text-muted-foreground" title={details?.title}>
          {details?.title ?? ''}
        </span>
        {details !== null && !isPinned ? (
          <IconButton label="Pin" onClick={pin}>
            <Pin />
          </IconButton>
        ) : null}
        <IconButton label={widened ? 'Return to width' : 'Widen the inspector'} onClick={toggleWidened}>
          {widened ? <Minimize2 /> : <Maximize2 />}
        </IconButton>
        <IconButton label="Close the inspector" shortcut="inspector" onClick={closeInspector}>
          <PanelRightClose />
        </IconButton>
      </div>
      {narrow && pinned.length > 0 ? (
        <div className="border-b px-2 py-1">
          <PinChips />
        </div>
      ) : null}
      <div className="@container min-h-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </aside>
  )
}
