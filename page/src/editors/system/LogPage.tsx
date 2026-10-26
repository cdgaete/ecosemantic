import { useEffect, useState } from 'react'
import { colourOfEntry } from '@/activity/agents'
import { Digest } from '@/activity/Digest'
import { holds, type DigestFilter } from '@/activity/digest'
import { touches } from '@/activity/filters'
import { OpenTrails } from '@/activity/OpenTrails'
import { Trail } from '@/activity/Trail'
import { useCalls, useLog, useTrail } from '@/api/queries'
import type { Change, LogEntry, ProductSystem } from '@/api/types'
import { cn } from '@/lib/utils'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { formatAgo, shortHash } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { useUi } from '@/store/ui'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import type { SystemView } from './SystemEditor'

function nameOf(change: Change, system: ProductSystem): string {
  if (change.entity === 'process') {
    const process = system.processes.find((p) => p.id === change.id)
    return process ? `process ${process.code}` : `process ${change.id}`
  }
  if (change.entity === 'exchange') {
    for (const process of system.processes) {
      const exchange = process.exchanges.find((e) => e.id === change.id)
      if (exchange) return `exchange ${exchange.name} of ${process.code}`
    }
    return `exchange ${change.id}`
  }
  return `${change.entity} ${change.id}`
}

function describe(change: Change, system: ProductSystem): string {
  const target = nameOf(change, system)
  if (change.op === 'add') return `added ${target}`
  if (change.op === 'delete') return `deleted ${target}`
  return `${target}: ${change.field} ${JSON.stringify(change.before)} → ${JSON.stringify(change.after)}`
}

function Entry({ entry, systemId, system, fresh }: { entry: LogEntry; systemId: string; system: ProductSystem; fresh: boolean }) {
  const chosen = useUi((s) => s.chosenEntry)
  const choose = useUi((s) => s.chooseEntry)
  const open = chosen !== null && chosen.systemId === systemId && chosen.seq === entry.seq
  const trail = useTrail(systemId, entry.seq, open)
  return (
    <li className={cn('border-b border-l-2 py-1 pl-1', open && 'bg-muted/40')} style={{ borderLeftColor: colourOfEntry(entry) }}>
      <button type="button" aria-expanded={open} className="flex w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-md px-2 py-1 text-left transition-colors duration-150 hover:bg-foreground/8" onClick={() => choose(open ? null : { systemId, seq: entry.seq, hash: entry.result_hash })}>
        <span className="tabular-nums text-muted-foreground">#{entry.seq}</span>
        <time dateTime={entry.timestamp} title={entry.timestamp} className="text-muted-foreground">
          {formatAgo(entry.timestamp)}
        </time>
        <span>
          {entry.actor.kind}
          {entry.actor.id ? ` ${entry.actor.id}` : entry.actor.name ? ` ${entry.actor.name}` : ''}
        </span>
        <span className="text-muted-foreground">{entry.source}</span>
        {fresh ? <span className="rounded-full bg-accent/15 px-1.5 text-xs font-semibold text-accent">NEW</span> : null}
        <span className="basis-full font-medium">{entry.message}</span>
        <span className="rounded-full bg-muted px-1.5 text-xs text-muted-foreground">
          {entry.changes.length} change{entry.changes.length === 1 ? '' : 's'}
        </span>
      </button>
      {open ? (
        <div className="px-2 pt-1 text-xs [overflow-wrap:anywhere]">
          <ul className="list-disc pl-4">
            {entry.changes.map((c, i) => (
              <li key={i}>{describe(c, system)}</li>
            ))}
          </ul>
          {trail.error ? <p className="text-destructive">{trail.error.message}</p> : null}
          {trail.data && trail.data.value.length > 0 ? <Trail calls={trail.data.value} /> : null}
          <AppLink to={paths.version(systemId, entry.result_hash)} className="text-accent">
            Open this version ({shortHash(entry.result_hash)})
          </AppLink>
        </div>
      ) : null}
    </li>
  )
}

export function LogPage({ view }: { view: SystemView }) {
  const log = useLog(view.id)
  const chosenProcess = useUi((s) => s.chosenProcess)
  const chooseProcess = useUi((s) => s.chooseProcess)
  const since = useUi((s) => s.since[view.id])
  const look = useUi((s) => s.look)
  const [counted, setCounted] = useState<DigestFilter | null>(null)
  const recorded = log.data?.value ?? []
  const latest = recorded.at(-1)?.seq ?? null
  useEffect(() => {
    if (latest !== null) look(view.id, latest)
  }, [look, view.id, latest])
  const fresh = since === undefined ? [] : recorded.filter((entry) => entry.seq > since)
  const from = since === undefined ? null : (recorded.find((entry) => entry.seq === since)?.timestamp ?? null)
  const calls = useCalls(view.id, from, fresh.length > 0)
  const failed = (calls.data?.value ?? []).filter((call) => call.outcome === 'error')
  const process = view.system.processes.find((p) => p.id === chosenProcess) ?? null
  const entries = [...recorded]
    .reverse()
    .filter((entry) => process === null || touches(entry, process))
    .filter((entry) => counted === null || counted === 'failed' || (since !== undefined && entry.seq > since && holds(entry, counted)))
  return (
    <>
      <EditorHeader icon="log" page="Log" entity={view.system.name} />
      {since !== undefined && latest !== null ? <Digest systemId={view.id} since={since} latest={latest} fresh={fresh} failed={failed.length} filter={counted} onFilter={setCounted} /> : null}
      {process !== null ? (
        <p className="flex items-center gap-2 px-4 pt-2 text-xs">
          Process: {process.name}
          <button type="button" aria-label="Clear process filter" className="opacity-60 hover:opacity-100" onClick={() => chooseProcess(null)}>
            ✕
          </button>
        </p>
      ) : null}
      <OpenTrails systemId={view.id} />
      <Section title="Entries" sectionKey={`system:${view.id}:log`} actions={view.version ? undefined : <RequestAction systemId={view.id} entity="product_system" entityId={view.system.id} />}>
        {log.error ? <p className="text-destructive">{log.error.message}</p> : null}
        {counted === 'failed' ? (
          <Trail calls={failed} />
        ) : (
          <ul>
            {entries.map((entry) => (
              <Entry key={entry.seq} entry={entry} systemId={view.id} system={view.system} fresh={since !== undefined && entry.seq > since} />
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}
