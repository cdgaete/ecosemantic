import type { ReactNode } from 'react'
import { useLocation, useMatch } from 'react-router-dom'
import { useServer, useSystem } from '@/api/queries'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { RequestsBadge, ValidationBadge } from './Badges'
import { NARROW_BELOW } from './inspector'
import { LiveStatus } from './LiveStatus'
import { pageTitle } from './pageTitle'
import { PinChips } from './PinChips'
import { useMinWidth } from './useMinWidth'

function PageName({ graph, narrow }: { graph: string | null; narrow: boolean }) {
  const { pathname } = useLocation()
  const title = pageTitle(pathname)
  return (
    <>
      <div className={cn('flex min-w-0 items-center gap-2', narrow && 'flex-1')}>
        <h1 className={cn('line-clamp-2 text-base font-semibold [overflow-wrap:anywhere]', narrow && 'min-w-0 flex-1')} title={title}>
          {title}
        </h1>
        {graph === null ? null : (
          <AppLink to={paths.system(graph)} className="shrink-0 self-start rounded-md px-2 py-0.5 text-xs text-accent hover:underline">
            Graph
          </AppLink>
        )}
      </div>
      <PinChips />
    </>
  )
}

export function NameIsland({ menus, systemId }: { menus: ReactNode; systemId: string | null }) {
  const explorer = useMatch('/databases/:name/*') !== null
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  const read = useSystem(systemId ?? '', systemId !== null)
  const client = useServer().data?.client ?? null
  const name = read.data?.value.name ?? ''
  const narrow = !useMinWidth(NARROW_BELOW)
  const labelled = useMinWidth(1280)
  return (
    <header
      data-clear="top"
      className={cn(
        'col-start-2 row-start-1 min-w-0 rounded-xl border bg-chrome/95 shadow-lg',
        narrow
          ? 'flex flex-wrap items-center justify-self-stretch gap-x-3 gap-y-1 px-3 py-1'
          : 'flex max-w-[min(560px,100%)] flex-col justify-self-start gap-1 px-3 pt-1 pb-2',
      )}
    >
      {menus === null ? null : <div className="border-b pb-1">{menus}</div>}
      {systemId === null ? (
        <PageName graph={explorer ? canvasSystemId : null} narrow={narrow} />
      ) : (
        <>
          <h1 className={cn('line-clamp-2 text-base font-semibold [overflow-wrap:anywhere]', narrow && 'min-w-0 flex-1')} title={name}>
            {name}
          </h1>
          {narrow ? (
            <LiveStatus short />
          ) : (
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <ValidationBadge id={systemId} />
              <RequestsBadge id={systemId} />
              <LiveStatus short={!labelled} />
              {client === null ? null : (
                <span className="min-w-0 truncate" title={`Connected: ${client.name}`}>
                  Connected: {client.name}
                </span>
              )}
            </div>
          )}
          {narrow ? null : <PinChips />}
        </>
      )}
    </header>
  )
}
