import { Maximize2, Minimize2, PanelRightClose, Pin, Waypoints } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { IconButton } from './IconButton'
import { useMinWidth } from './useMinWidth'

const VIEW = 'rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'
const CURRENT = 'bg-background text-foreground shadow-sm'

export function Panel() {
  const systemId = useUi((s) => s.canvasSystemId)
  const details = useUi((s) => s.details)
  const lastDetails = useUi((s) => s.lastDetails)
  const pinned = useUi((s) => s.pinned)
  const expanded = useUi((s) => s.panelMode === 'expanded')
  const setPanelMode = useUi((s) => s.setPanelMode)
  const setGraphCovered = useUi((s) => s.setGraphCovered)
  const pin = useUi((s) => s.pin)
  const beside = useMinWidth(768)
  const isPinned = details !== null && pinned.some((p) => p.id === details.id)
  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex items-center gap-1 border-b bg-chrome p-1">
        {systemId ? (
          <>
            <AppLink to={paths.system(systemId)} aria-current={details === null ? 'page' : undefined} className={cn(VIEW, details === null && CURRENT)}>
              Activity
            </AppLink>
            <AppLink to={details?.path ?? lastDetails?.path ?? paths.systemPage(systemId, 'general')} aria-current={details !== null ? 'page' : undefined} className={cn(VIEW, details !== null && CURRENT)}>
              Details
            </AppLink>
          </>
        ) : null}
        <span className="min-w-0 flex-1 truncate px-2.5 text-xs text-muted-foreground" title={details?.title}>
          {details?.title ?? ''}
        </span>
        {details !== null && !isPinned ? (
          <IconButton label="Pin" onClick={pin}>
            <Pin />
          </IconButton>
        ) : null}
        {systemId === null ? null : beside ? (
          <>
            <IconButton label={expanded ? 'Show graph' : 'Expand panel'} onClick={() => setPanelMode(expanded ? 'beside' : 'expanded')}>
              {expanded ? <Minimize2 /> : <Maximize2 />}
            </IconButton>
            <IconButton label="Collapse panel" shortcut="panel" onClick={() => setPanelMode('collapsed')}>
              <PanelRightClose />
            </IconButton>
          </>
        ) : (
          <IconButton label="Show graph" onClick={() => setGraphCovered(false)}>
            <Waypoints />
          </IconButton>
        )}
      </div>
      <div className="@container min-h-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
