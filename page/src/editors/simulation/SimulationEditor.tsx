import { useParams } from 'react-router-dom'
import { useCancelRun, useRun, useSystem } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import type { Drawn, Method, MonteCarloResult, ProductSystem, Run, Scope, Stopped } from '@/api/types'
import { Button } from '@/components/ui/button'
import { backwardsTreatmentNote, categoryLabel, creditLoopNote, formatAmount, methodById, shortHash, formatAgo } from '@/lib/format'
import { movedSince } from '@/lib/hashes'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { RequestAction } from '@/requests/RequestAction'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid, PENDING } from '@/window/FieldGrid'
import { Section } from '@/window/Section'
import { useEditorTab } from '@/window/useEditorTab'
import { SimulationResults } from './SimulationResults'

const UNCERTAINTY_IN: Record<Scope, string> = { full: 'all exchanges', biosphere_only: 'elementary flows only' }

function iterations(run: Run): string {
  const { n, n_min, n_max, rel_se_target } = run.config
  return n !== null ? `${n}, fixed` : `${n_min} to ${n_max}, until every median's relative standard error is under ${rel_se_target}`
}

function demand(run: Run, system: ProductSystem | undefined): string {
  const names = new Map((system?.processes ?? []).map((p) => [p.code, p.name]))
  return run.demand.map((d) => `${d.ref.kind === 'foreground' ? (names.get(d.ref.code) ?? d.ref.code) : d.ref.id} × ${formatAmount(d.amount)}`).join('; ')
}

function heldAtAmount(count: number): string | null {
  if (count === 0) return null
  return count === 1
    ? '1 background normal distribution held at its amount, its standard deviation exceeding it.'
    : `${formatAmount(count)} background normal distributions held at their amount, their standard deviation exceeding it.`
}

function counted(count: number, one: string, many: string): string {
  return `${formatAmount(count)} ${count === 1 ? one : many}`
}

function drawnLine({ parameters, foreground, background }: Drawn): string {
  return [
    counted(parameters.drawn, 'parameter', 'parameters'),
    `${formatAmount(foreground.drawn)} of ${counted(foreground.there, 'foreground exchange', 'foreground exchanges')}`,
    `${formatAmount(background.drawn)} of ${counted(background.there, 'background exchange', 'background exchanges')}`,
  ].join(', ')
}

function dropped(result: MonteCarloResult): string | null {
  const count = result.dropped_draws.length
  if (count === 0) return null
  const loops = [...result.dropped_loops.map((codes) => codes.join(', ')), ...result.dropped_background.map((name) => `in the background, ${name}`)].join('; ')
  return `${count} of ${result.n + count} draws were dropped: in each, a process or loop made no more than it used (${loops}).`
}

const STOPPED: Record<Stopped, string> = {
  target: 'reached its target error',
  ceiling: 'reached n_max before its target error',
  fixed: 'ran its stated count',
  cancelled: 'stopped on request',
}

function ran(result: MonteCarloResult, methods: Method[]): string {
  const taken = result.n + result.dropped_draws.length
  const kept = taken === result.n ? `${result.n} ${result.n === 1 ? 'iteration' : 'iterations'}` : `${result.n} of ${taken} iterations kept`
  const held = result.gating_method === null ? '' : `, held longest by ${categoryLabel(methodById(methods, result.gating_method))}`
  return `${kept}, ${STOPPED[result.stopped]}${held}`
}

function named(ids: string[], methods: Method[]): string {
  return ids.map((id) => categoryLabel(methodById(methods, id))).join(', ')
}

function When({ instant }: { instant: string }) {
  return <span title={instant}>{formatAgo(instant)}</span>
}

export function SimulationEditor() {
  const { id = '', runId = '' } = useParams()
  const go = useGo()
  useSystemStream(id, go)
  const read = useSystem(id)
  const system = read.data?.value
  const answer = useRun(runId)
  const cancel = useCancelRun(runId, id)
  useEditorTab({ id: `simulation:${runId}`, kind: 'simulation', title: `Simulation of: ${system?.name ?? ''}`, path: paths.simulation(id, runId) })
  if (answer.error) return <p className="p-4 text-destructive">{answer.error.message}</p>
  if (!answer.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  const run = answer.data.value
  const moved = movedSince(run.at_hash, system?.hash)
  const action = <RequestAction systemId={id} entity="product_system" entityId={id} />
  const worst = run.progress.worst_rel_se === null ? '–' : formatAmount(run.progress.worst_rel_se)
  const note = run.result ? heldAtAmount(run.result.drawn.background.held) : null
  const drops = run.result ? dropped(run.result) : null
  return (
    <>
      <EditorHeader icon="simulation" page="Monte Carlo Simulation" entity={system?.name ?? ''} />
      <Section title="Settings" sectionKey={`simulation:${runId}:settings`} actions={action}>
        <FieldGrid
          rows={[
            { label: 'Product system', value: read.isPending ? PENDING : system?.name ?? '' },
            { label: 'Demand', value: read.isPending ? PENDING : demand(run, system) },
            { label: 'Impact method', value: run.methods[0]?.impact_method ?? '' },
            { label: 'Iterations', value: iterations(run) },
            { label: 'Seed', value: String(run.config.seed) },
            { label: 'Uncertainty in', value: UNCERTAINTY_IN[run.config.scope] },
            {
              label: 'Computed on',
              value: (
                <span className="flex flex-wrap items-center gap-2">
                  <AppLink to={paths.version(id, run.at_hash)} className="underline">
                    {shortHash(run.at_hash)}
                  </AppLink>
                  {moved ? <span className="text-warning">The model has changed since this simulation started.</span> : null}
                </span>
              ),
            },
          ]}
        />
      </Section>
      <Section title="Progress" sectionKey={`simulation:${runId}:progress`} actions={action}>
        <FieldGrid
          rows={[
            { label: 'Status', value: run.status },
            { label: 'Iterations taken', value: String(run.progress.iterations) },
            { label: 'Worst median relative SE', value: `${worst}, target ${run.config.rel_se_target}` },
            { label: 'Posted', value: <When instant={run.posted_at} /> },
            { label: 'Started', value: run.started_at === null ? '–' : <When instant={run.started_at} /> },
            { label: 'Finished', value: run.finished_at === null ? '–' : <When instant={run.finished_at} /> },
          ]}
        />
        {run.open ? (
          <div className="pt-3">
            <Button size="sm" disabled={run.cancel_requested || cancel.isPending} onClick={() => cancel.mutate()}>
              {run.cancel_requested ? 'Stopping…' : 'Cancel'}
            </Button>
          </div>
        ) : null}
        {cancel.error ? <p className="pt-2 text-destructive">{cancel.error.message}</p> : null}
        {run.error ? <p className="pt-2 text-destructive">{run.error.message}</p> : null}
      </Section>
      <Section title="Results" sectionKey={`simulation:${runId}:results`} actions={action}>
        {run.treatments_run_backwards.map((named) => (
          <p key={named} className="pb-2 text-warning">
            {backwardsTreatmentNote(named)}
          </p>
        ))}
        {run.result ? (
          <>
            <p className="pb-2">Drawn: {drawnLine(run.result.drawn)}</p>
            {note ? <p className="pb-2 text-muted-foreground">{note}</p> : null}
            <p className="pb-2">{ran(run.result, run.methods)}</p>
            {run.result.constant.length > 0 ? (
              <p className="pb-2 text-muted-foreground">Met as constant, every draw equal: {named(run.result.constant, run.methods)}.</p>
            ) : null}
            {run.result.indistinguishable_from_zero.length > 0 ? (
              <p className="pb-2 text-muted-foreground">Left out of the stop rule, their median indistinguishable from zero: {named(run.result.indistinguishable_from_zero, run.methods)}.</p>
            ) : null}
            {drops ? <p className="pb-2 text-warning">{drops}</p> : null}
            {run.result.credit_loops.map((codes) => (
              <p key={codes.join(' ')} className="pb-2 text-warning">
                {creditLoopNote(codes)}
              </p>
            ))}
            <SimulationResults result={run.result} methods={run.methods} systemId={run.product_system_id} />
          </>
        ) : (
          <p className="text-muted-foreground">{run.open ? 'The results appear when the simulation finishes.' : 'This simulation holds no result.'}</p>
        )}
      </Section>
    </>
  )
}
