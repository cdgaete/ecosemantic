import { Maximize2, Minimize2, PanelRightClose, Pin } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { IconButton } from './IconButton'
import { closeInspector, NARROW_BELOW, toggleWidened, useInspectorShown } from './inspector'
import { PinChips } from './PinChips'
import { useMinWidth } from './useMinWidth'

const VIEW = 'rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'
const CURRENT = 'bg-background text-foreground shadow-sm'

export function Inspector() {
  const shown = useInspectorShown()
  const narrow = !useMinWidth(NARROW_BELOW)
  const systemId = useUi((s) => s.canvasSystemId)
  const details = useUi((s) => s.details)
  const lastDetails = useUi((s) => s.lastDetails)
  const pinned = useUi((s) => s.pinned)
  const widened = useUi((s) => s.inspector === 'widened')
  const pin = useUi((s) => s.pin)
  const isPinned = details !== null && pinned.some((p) => p.id === details.id)
  if (!shown) return null
  return (
    <aside
      aria-label="Inspector"
      data-clear={narrow ? undefined : 'right'}
      className={cn(
        'flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-background shadow-lg',
        narrow
          ? cn('col-span-2 col-start-1', widened ? 'row-span-2 row-start-1 self-stretch' : 'row-span-1 row-start-2 h-[62%] self-end')
          : cn('col-start-3 row-span-2 row-start-2 justify-self-end', widened ? 'w-[min(840px,60vw)]' : 'w-[360px] min-[1280px]:w-[400px]'),
      )}
    >
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
