import { ArrowLeft, History, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { said } from '@/activity/digest'
import { useLog, useServer, useSystem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { RequestsBadge, ValidationBadge } from './Badges'
import { DetailLink } from './DetailLink'
import { NARROW_BELOW } from './inspector'
import { LiveStatus } from './LiveStatus'
import { pageTitle } from './pageTitle'
import { PinChips } from './PinChips'
import { useSheet, type SheetReturn } from './sheets'
import { useMinWidth } from './useMinWidth'

function BackButton({ back }: { back: SheetReturn }) {
  return (
    <Button asChild size="sm" className="h-7 shrink-0">
      <AppLink to={back.to}>
        <ArrowLeft /> {back.label}
      </AppLink>
    </Button>
  )
}

function BuildButton({ back, entries }: { back: SheetReturn; entries: number }) {
  const go = useGo()
  return (
    <Button
      size="sm"
      variant="ghost"
      className="h-5 shrink-0 px-1"
      title="Back to the graph and its build timeline"
      onClick={() => go(back.to)}
    >
      <History /> {`Build · ${said(entries, 'entry', 'entries')}`}
    </Button>
  )
}

const DETAILS = 'Product system details'

function SystemName({ name, systemId }: { name: string; systemId: string }) {
  return (
    <DetailLink
      to={paths.systemPage(systemId, 'general')}
      className="group rounded-sm hover:underline focus-visible:underline focus-visible:outline-2 focus-visible:outline-ring"
    >
      {name}
      <span
        role="img"
        aria-label={DETAILS}
        title={DETAILS}
        className="whitespace-nowrap text-muted-foreground transition-colors duration-150 group-hover:text-foreground"
      >
        {' '}
        <Info aria-hidden="true" className="inline size-3.5 align-[-0.15em]" />
      </span>
    </DetailLink>
  )
}

function PageName({ back, narrow }: { back: SheetReturn | null; narrow: boolean }) {
  const { pathname } = useLocation()
  const title = pageTitle(pathname)
  return (
    <>
      <div className={cn('flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1', narrow && 'flex-1')}>
        {back === null ? null : <BackButton back={back} />}
        <h1 className={cn('line-clamp-2 text-base font-semibold [overflow-wrap:anywhere]', narrow && 'min-w-0 flex-1')} title={title}>
          {title}
        </h1>
      </div>
      <PinChips />
    </>
  )
}

export function NameIsland({ menus, systemId }: { menus: ReactNode; systemId: string | null }) {
  const back = useSheet()
  const read = useSystem(systemId ?? '', systemId !== null)
  const log = useLog(systemId ?? '', systemId !== null)
  const entries = log.data?.value.length ?? 0
  const client = useServer().data?.client ?? null
  const name = read.data?.value.name ?? ''
  const narrow = !useMinWidth(NARROW_BELOW)
  const labelled = useMinWidth(1280)
  return (
    <header
      data-clear="top"
      className={cn(
        'row-start-1 min-w-0 rounded-xl border bg-chrome/95 shadow-lg',
        narrow
          ? 'col-start-2 flex flex-wrap items-center justify-self-stretch gap-x-3 gap-y-1 px-3 py-1'
          : 'col-start-1 flex max-w-[min(560px,100%)] flex-col justify-self-start gap-1 px-3 pt-1 pb-2',
      )}
    >
      {menus === null ? null : <div className="border-b pb-1">{menus}</div>}
      {systemId === null ? (
        <PageName back={back} narrow={narrow} />
      ) : (
        <>
          <div className={cn('flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1', narrow && 'flex-1')}>
            {back === null ? null : <BackButton back={back} />}
            <h1 className={cn('line-clamp-2 text-base font-semibold [overflow-wrap:anywhere]', narrow && 'min-w-0 flex-1')} title={name}>
              <SystemName name={name} systemId={systemId} />
            </h1>
          </div>
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
              {back?.docked === true ? <BuildButton back={back} entries={entries} /> : null}
            </div>
          )}
          {narrow ? null : <PinChips />}
        </>
      )}
    </header>
  )
}
