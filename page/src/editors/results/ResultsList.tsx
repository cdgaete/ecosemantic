import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { colourOf } from '@/activity/agents'
import { useCalculations, useSystem } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import type { Call } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatAgo, formatAmount, shortHash } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import { useEditorTab } from '@/window/useEditorTab'
import { methodOf, variantsOf, withoutDatabase } from './recorded'

function Who({ call }: { call: Call }) {
  if (call.origin === 'view') return <span>you</span>
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block size-2 rounded-full" style={{ backgroundColor: colourOf(call.agent) }} />
      {call.agent}
    </span>
  )
}

function Calculation({ call, systemId, database, current }: { call: Call; systemId: string; database: string; current: string }) {
  const [unfolded, setUnfolded] = useState(false)
  const scores = call.summary?.scores ?? []
  const variants = variantsOf(call)
  const earlier = call.at_hash !== null && call.at_hash !== current
  return (
    <li className="border-b py-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <Who call={call} />
        <time dateTime={call.started_at} title={call.started_at} className="text-muted-foreground">
          {formatAgo(call.started_at)}
        </time>
        {call.outcome === 'ok' ? (
          <AppLink to={paths.results(systemId, 'impact', `?call=${call.id}`)} className="ml-auto text-accent hover:underline">
            Open
          </AppLink>
        ) : null}
      </div>
      <p className="font-medium break-words">{methodOf(call, database)}</p>
      <p className="text-muted-foreground">{variants.length > 0 ? variants.join(', ') : 'base values'}</p>
      {(unfolded ? scores : scores.slice(0, 1)).map((score, at) => (
        <p key={`${score.method}-${at}`} className="break-words">
          {withoutDatabase(score.method, database)}: <span className="tabular-nums">{formatAmount(score.value)}</span> {score.unit}
        </p>
      ))}
      {scores.length > 1 ? (
        <button type="button" aria-expanded={unfolded} className="text-xs text-accent hover:underline" onClick={() => setUnfolded(!unfolded)}>
          {unfolded ? 'Show the first score only' : `and ${scores.length - 1} more`}
        </button>
      ) : null}
      {call.error ? <p className="text-destructive">{call.error.message}</p> : null}
      {call.at_hash !== null ? (
        <p className="text-xs text-muted-foreground">
          on {shortHash(call.at_hash)}
          {earlier ? <span className="text-warning"> · an earlier version</span> : null}
        </p>
      ) : null}
    </li>
  )
}

export function ResultsList() {
  const { id = '' } = useParams()
  const go = useGo()
  useSystemStream(id, go)
  const read = useSystem(id)
  const calculations = useCalculations(id)
  const system = read.data?.value
  useEditorTab({ id: `results-list:${id}`, kind: 'results', title: `Results – ${system?.name ?? ''}`, path: paths.resultList(id) })
  const recorded = calculations.data?.value ?? []
  const start = (
    <Button size="sm" onClick={() => go(paths.results(id, 'setup', ''))}>
      <Plus className="size-3.5" /> New calculation
    </Button>
  )
  return (
    <>
      <EditorHeader icon="result" page="Results" entity={system?.name ?? ''} actions={start} />
      <Section title="Calculations" sectionKey={`results-list:${id}`}>
        {calculations.error ? <p className="text-destructive">{calculations.error.message}</p> : null}
        {!calculations.data && !calculations.error ? <p className="text-muted-foreground">Loading…</p> : null}
        {calculations.data && recorded.length === 0 ? <p className="text-muted-foreground">No calculation is recorded for this system yet. Calculate one, or ask the agent to.</p> : null}
        <ul className="text-[12.5px]">
          {recorded.map((call) => (
            <Calculation key={call.id} call={call} systemId={id} database={system?.database.name ?? ''} current={system?.hash ?? ''} />
          ))}
        </ul>
      </Section>
    </>
  )
}
