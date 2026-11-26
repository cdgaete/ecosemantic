import { useDatabases, useHome, useSources } from '@/api/queries'
import type { LogEntry, SystemCard, SystemRow } from '@/api/types'
import { formatAgo } from '@/lib/format'
import { distinguishingId, sharedNames } from '@/lib/names'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { useUi } from '@/store/ui'
import { CanvasBadge, ValidationMark } from '@/window/Badges'
import { DataTable, type Column } from '@/window/DataTable'
import { Icon } from '@/window/Icon'
import { NARROW_BELOW } from '@/window/inspector'
import { useMinWidth } from '@/window/useMinWidth'
import { SourceList } from './databases/SourceList'

function Name({ card, shared, current }: { card: SystemCard; shared: Set<string>; current: boolean }) {
  const id = distinguishingId(card, shared)
  const narrow = !useMinWidth(NARROW_BELOW)
  return (
    <span className="block min-w-0">
      <AppLink to={paths.systemEntry(card.id, narrow)} aria-current={current ? 'true' : undefined} className="flex items-center gap-2 font-medium hover:underline">
        <Icon name="system" />
        <span className="break-words">{card.name}</span>
        {id ? <span className="shrink-0 text-xs font-normal text-muted-foreground">{id}</span> : null}
        {current ? <CanvasBadge /> : null}
      </AppLink>
      {card.description ? (
        <span className="line-clamp-2 text-xs text-muted-foreground" title={card.description}>
          {card.description}
        </span>
      ) : null}
    </span>
  )
}

function LastChange({ last }: { last: LogEntry }) {
  return (
    <span>
      #{last.seq} {last.actor.id ?? last.actor.name ?? last.actor.kind}{' '}
      <time dateTime={last.timestamp} title={last.timestamp} className="text-muted-foreground">
        {formatAgo(last.timestamp)}
      </time>
    </span>
  )
}

function OpenRequests({ id, open }: { id: string; open: number }) {
  return open > 0 ? (
    <AppLink to={paths.systemPage(id, 'requests')} className="hover:underline">
      {open} open
    </AppLink>
  ) : null
}

function columns(shared: Set<string>, canvasSystemId: string | null): Column<SystemRow>[] {
  return [
    { key: 'name', header: 'Name', width: 'rest', render: (row) => <Name card={row.system} shared={shared} current={row.system.id === canvasSystemId} /> },
    { key: 'database', header: 'Database', width: 'content', render: (row) => row.system.database },
    { key: 'processes', header: 'Processes', align: 'right', width: 'content', render: (row) => row.processes },
    { key: 'change', header: 'Last change', width: 'content', render: (row) => <LastChange last={row.last} /> },
    {
      key: 'validation',
      header: 'Validation',
      width: 'content',
      render: (row) => (
        <ValidationMark
          id={row.system.id}
          issues={row.validation ? row.validation.errors.length : null}
          error={row.unvalidated ? row.unvalidated.message : null}
        />
      ),
    },
    { key: 'requests', header: 'Requests', width: 'content', render: (row) => <OpenRequests id={row.system.id} open={row.open_requests} /> },
  ]
}

export function Welcome() {
  const home = useHome()
  const databases = useDatabases()
  const sources = useSources()
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  const go = useGo()
  const rows = home.data?.value ?? []
  const shared = sharedNames(rows.map((row) => row.system))
  const installed = databases.data?.value ?? []
  const database = installed[0]?.name ?? null
  return (
    <div className="p-4 text-sm">
      <h1 className="mb-2 text-base font-semibold">Product systems</h1>
      {home.data === undefined && home.error === null ? (
        <p role="status" className="text-muted-foreground">
          Loading the product systems…
        </p>
      ) : null}
      {home.error ? <p className="text-destructive">{home.error.message}</p> : null}
      {rows.length > 0 ? <DataTable columns={columns(shared, canvasSystemId)} rows={rows} rowKey={(row) => row.system.id} /> : null}
      {home.data && rows.length === 0 && databases.data && installed.length === 0 ? (
        <div className="flex max-w-md flex-col gap-2">
          <p className="text-muted-foreground">No background database is installed. Install one to model on:</p>
          <SourceList sources={sources.data?.value ?? []} onPick={() => go(paths.databases())} />
        </div>
      ) : null}
      {home.data && rows.length === 0 && database !== null ? (
        <p className="text-muted-foreground">
          Ask your chatbot for a model, for example: "On {database}, model one bicycle frame of 2 kg of low-alloyed steel and calculate its climate change score."
        </p>
      ) : null}
    </div>
  )
}
