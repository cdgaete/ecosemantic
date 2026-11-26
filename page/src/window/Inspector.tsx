import { ArrowLeft, Maximize2, Minimize2, PanelRightClose, PanelRightOpen, Pin } from 'lucide-react'
import { useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi, type EditorKind } from '@/store/ui'
import { IconButton } from './IconButton'
import { useSheetCover } from './cover'
import { closeInspector, NARROW_BELOW, openInspector, resizeInspector, toggleSheetHeight, toggleWidened, useInspectorShown } from './inspector'
import { PinChips } from './PinChips'
import { ResizeEdge } from './ResizeEdge'
import { returnLabel } from './sheets'
import { WIDEST_SHARE } from './resize'
import { useMinWidth } from './useMinWidth'

const VIEW = 'rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'
const CURRENT = 'bg-background text-foreground shadow-sm'
const NOUN_OF: Record<EditorKind, string> = { system: 'product system', process: 'process', results: 'result', simulation: 'Monte Carlo run', explorer: 'dataset' }
const SHEET_HEIGHT = { ordinary: 'h-[62%]', short: 'h-[38%]' } as const

export function Inspector() {
  const shown = useInspectorShown()
  const narrow = !useMinWidth(NARROW_BELOW)
  const systemId = useUi((s) => s.canvasSystemId)
  const details = useUi((s) => s.details)
  const lastDetails = useUi((s) => s.lastDetails)
  const pinned = useUi((s) => s.pinned)
  const widened = useUi((s) => s.inspector === 'widened')
  const sheetShort = useUi((s) => s.sheetShort)
  const kept = useUi((s) => s.inspectorWidth)
  const pin = useUi((s) => s.pin)
  const unpin = useUi((s) => s.unpin)
  const panel = useRef<HTMLElement>(null)
  const held = useRef(() => panel.current)
  const [dragged, setDragged] = useState<number | null>(null)
  const { pathname } = useLocation()
  const isPinned = details !== null && pinned.some((p) => p.id === details.id)
  useSheetCover(panel, narrow && shown)
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
      style={narrow || widened ? undefined : { maxWidth: `${WIDEST_SHARE * 100}vw`, ...(width === null ? {} : { width: `${width}px` }) }}
      className={cn(
        'relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-background shadow-lg',
        narrow
          ? cn('col-span-2 col-start-1', widened ? 'row-span-2 row-start-1 self-stretch' : cn('row-span-1 row-start-2 self-end', SHEET_HEIGHT[sheetShort ? 'short' : 'ordinary']))
          : widened
            ? 'col-span-2 col-start-2 row-span-2 row-start-2 z-10'
            : 'col-start-3 row-span-2 row-start-2 w-[360px] justify-self-end min-[1280px]:w-[400px]',
      )}
    >
      {narrow ? null : <ResizeEdge label="Resize the inspector" panel={held.current} width={width} onDrag={setDragged} onDrop={resizeInspector} onReset={() => resizeInspector(null)} />}
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
          <IconButton label={`Pin ${NOUN_OF[details.kind]} for quick access`} onClick={pin}>
            <Pin />
          </IconButton>
        ) : null}
        {details !== null && isPinned ? (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Unpin ${NOUN_OF[details.kind]}`}
            aria-pressed={true}
            className="h-7 shrink-0 bg-foreground/8 px-2 text-xs hover:bg-foreground/12"
            onClick={() => unpin(details.id)}
          >
            <Pin /> Pinned
          </Button>
        ) : null}
        <IconButton label={widened ? 'Return to width' : 'Widen the inspector'} onClick={toggleWidened}>
          {widened ? <Minimize2 /> : <Maximize2 />}
        </IconButton>
        {narrow && !widened ? (
          <Button size="sm" variant="ghost" className="h-7 shrink-0 px-2 text-xs" onClick={toggleSheetHeight}>
            {sheetShort ? 'Show more details' : 'Show more graph'}
          </Button>
        ) : null}
        {narrow ? (
          <Button size="sm" variant="ghost" className="h-7 shrink-0 px-2 text-xs" onClick={closeInspector}>
            <ArrowLeft /> {returnLabel(pathname)}
          </Button>
        ) : (
          <IconButton label="Close the inspector" shortcut="inspector" onClick={closeInspector}>
            <PanelRightClose />
          </IconButton>
        )}
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
