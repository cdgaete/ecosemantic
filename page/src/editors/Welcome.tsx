import { useDatabases, useLog, useSources, useSystem, useSystems } from '@/api/queries'
import type { SystemCard } from '@/api/types'
import { formatAgo } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { ValidationBadge } from '@/window/Badges'
import { DataTable, type Column } from '@/window/DataTable'
import { Icon } from '@/window/Icon'
import { SourceList } from './databases/SourceList'

function Name({ card }: { card: SystemCard }) {
  return (
    <span className="block min-w-0">
      <AppLink to={paths.system(card.id)} className="flex items-center gap-2 font-medium hover:underline">
        <Icon name="system" />
        <span className="break-words">{card.name}</span>
      </AppLink>
      {card.description ? (
        <span className="line-clamp-2 text-xs text-muted-foreground" title={card.description}>
          {card.description}
        </span>
      ) : null}
    </span>
  )
}

function ProcessCount({ id }: { id: string }) {
  const read = useSystem(id)
  return <>{read.data ? read.data.value.processes.length : ''}</>
}

function LastChange({ id }: { id: string }) {
  const log = useLog(id)
  const last = log.data?.value.at(-1)
  if (!last) return null
  return (
    <span>
      #{last.seq} {last.actor.id ?? last.actor.name ?? last.actor.kind}{' '}
      <time dateTime={last.timestamp} title={last.timestamp} className="text-muted-foreground">
        {formatAgo(last.timestamp)}
      </time>
    </span>
  )
}

function OpenRequests({ id }: { id: string }) {
  const read = useSystem(id)
  const open = read.data?.open_requests ?? 0
  return open > 0 ? (
    <AppLink to={paths.systemPage(id, 'requests')} className="hover:underline">
      {open} open
    </AppLink>
  ) : null
}

const COLUMNS: Column<SystemCard>[] = [
  { key: 'name', header: 'Name', render: (card) => <Name card={card} /> },
  { key: 'database', header: 'Database', render: (card) => card.database },
  { key: 'processes', header: 'Processes', align: 'right', render: (card) => <ProcessCount id={card.id} /> },
  { key: 'change', header: 'Last change', render: (card) => <LastChange id={card.id} /> },
  { key: 'validation', header: 'Validation', render: (card) => <ValidationBadge id={card.id} /> },
  { key: 'requests', header: 'Requests', render: (card) => <OpenRequests id={card.id} /> },
]

export function Welcome() {
  const systems = useSystems()
  const databases = useDatabases()
  const sources = useSources()
  const go = useGo()
  const cards = systems.data?.value ?? []
  const installed = databases.data?.value ?? []
  const database = installed[0]?.name ?? null
  return (
    <div className="p-4 text-sm">
      <h1 className="mb-2 text-base font-semibold">Product systems</h1>
      {systems.error ? <p className="text-destructive">{systems.error.message}</p> : null}
      {cards.length > 0 ? <DataTable columns={COLUMNS} rows={cards} rowKey={(card) => card.id} /> : null}
      {systems.data && cards.length === 0 && databases.data && installed.length === 0 ? (
        <div className="flex max-w-md flex-col gap-2">
          <p className="text-muted-foreground">No background database is installed. Install one to model on:</p>
          <SourceList sources={sources.data?.value ?? []} onPick={() => go(paths.databases())} />
        </div>
      ) : null}
      {systems.data && cards.length === 0 && database !== null ? (
        <p className="text-muted-foreground">
          Ask your chatbot for a model, for example: "On {database}, model one bicycle frame of 2 kg of low-alloyed steel and calculate its climate change score."
        </p>
      ) : null}
    </div>
  )
}
