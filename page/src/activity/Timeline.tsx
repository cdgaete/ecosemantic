import { useQueries } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { openTrailQuery, useAgents, useLog } from '@/api/queries'
import type { Call } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatAgo } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { cn } from '@/lib/utils'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useInspectorShown, openInspector } from '@/window/inspector'
import { useWidth } from '@/window/useWidth'
import { actorOf, colourOfEntry, quietSince } from './agents'
import { digestOf, digestPhrases, said } from './digest'
import { timelineFits } from './timeline'

interface AtWork {
  agent: string
  lastCallAt: string
  calls: Call[]
}

function AgentCard({ work }: { work: AtWork }) {
  const quiet = quietSince(work.lastCallAt, Date.now())
  const earlier = work.calls.slice(0, -3)
  return (
    <li className="min-w-0 rounded-md border border-dashed border-chart-5 bg-background px-2 py-1.5">
      <p className="text-xs font-medium [overflow-wrap:anywhere]">
        {work.agent} ·{' '}
        {quiet ? (
          <>
            last active{' '}
            <time dateTime={work.lastCallAt} title={work.lastCallAt}>
              {formatAgo(work.lastCallAt)}
            </time>
          </>
        ) : (
          'work in progress'
        )}
      </p>
      <ul className="flex flex-col text-xs">
        {work.calls.slice(-3).map((call) => (
          <li key={call.id} className="min-w-0">
            <span className={cn('block truncate', call.outcome === 'error' && 'text-destructive')} title={`${call.tool} · ${call.outcome}`}>
              {`${call.tool} · ${call.outcome}`}
            </span>
          </li>
        ))}
      </ul>
      {earlier.length > 0 ? <p className="text-xs text-muted-foreground">{`+ ${said(earlier.length, 'earlier call', 'earlier calls')} in the full log`}</p> : null}
    </li>
  )
}

export function Timeline({ systemId }: { systemId: string }) {
  const shown = useInspectorShown()
  const go = useGo()
  const log = useLog(systemId)
  const agents = useAgents()
  const since = useUi((s) => s.since[systemId])
  const look = useUi((s) => s.look)
  const choose = useUi((s) => s.chooseEntry)
  const list = useRef<HTMLOListElement>(null)
  const width = useWidth(list)
  const recorded = log.data?.value ?? []
  const latest = recorded.at(-1)?.seq ?? null
  useEffect(() => {
    if (latest !== null) look(systemId, latest)
  }, [look, systemId, latest])
  const working = (agents.data?.value ?? []).filter((a) => a.origin === 'agent' && a.product_system_id === systemId)
  const trails = useQueries({ queries: working.map((a) => openTrailQuery(a.agent, systemId)) })
  const atWork: AtWork[] = working.flatMap((agent, i) => {
    const calls = trails[i]?.data?.value ?? []
    return calls.length === 0 ? [] : [{ agent: agent.agent, lastCallAt: agent.last_call_at, calls }]
  })
  const fits = timelineFits(width)
  const cards = atWork.slice(0, fits)
  const entries = [...recorded].reverse().slice(0, Math.max(0, fits - cards.length))
  const digest = digestOf(since === undefined ? [] : recorded.filter((entry) => entry.seq > since))
  const counts = digestPhrases(digest).filter(({ key }) => digest[key] > 0)
  return (
    <section
      aria-label="Build timeline"
      data-clear="bottom"
      className={cn('col-start-1 row-start-3 flex min-w-0 flex-col gap-2 rounded-xl border bg-chrome/95 p-2 shadow-lg', shown ? 'col-span-2' : 'col-span-3')}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1">
        <h2 className="text-sm font-semibold">Build</h2>
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">
          {counts.map(({ text }) => text).join(' · ')}
        </p>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            openInspector()
            go(paths.system(systemId))
          }}
        >
          {`Full log · ${said(recorded.length, 'entry', 'entries')}`}
        </Button>
        <Button size="sm" onClick={() => useRequestDialog.getState().open({ systemId })}>
          <Plus className="size-3.5" /> New request
        </Button>
      </div>
      <ol aria-label="Build cards" ref={list} className="grid grid-cols-[repeat(auto-fit,minmax(208px,1fr))] gap-2">
        {cards.map((work) => (
          <AgentCard key={work.agent} work={work} />
        ))}
        {entries.map((entry) => (
          <li key={entry.seq} className="min-w-0 rounded-md border border-l-2 bg-background" style={{ borderLeftColor: colourOfEntry(entry) }}>
            <button
              type="button"
              className="flex h-full w-full flex-col gap-0.5 rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-foreground/8"
              onClick={() => choose({ systemId, seq: entry.seq, hash: entry.result_hash })}
            >
              <span className="tabular-nums text-muted-foreground">{`#${entry.seq}`}</span>
              <span className="line-clamp-2 text-xs font-medium [overflow-wrap:anywhere]" title={entry.message}>
                {entry.message}
              </span>
              <span className="flex min-w-0 items-baseline gap-2 text-xs text-muted-foreground">
                <span className="min-w-0 truncate" title={actorOf(entry)}>
                  {actorOf(entry)}
                </span>
                <time dateTime={entry.timestamp} title={entry.timestamp} className="shrink-0">
                  {formatAgo(entry.timestamp)}
                </time>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}
