import { useState } from 'react'
import { useContributions } from '@/api/queries'
import { useCategory } from '@/lib/address'
import type { StageInput, StagePart } from '@/api/types'
import { categoryLabel, formatAmount, formatShare, methodById } from '@/lib/format'
import { stageColour, stageNames } from '@/lib/stageColours'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column, type SummaryRow } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

interface Row {
  key: string
  depth: number
  swatch: string | null
  name: string
  location: string | null
  share: number | null
  score: number
}

function inputRow(input: StageInput, key: string): Row {
  return {
    key,
    depth: 2,
    swatch: null,
    name: input.name,
    location: input.location,
    share: input.fraction,
    score: input.score,
  }
}

function rowsOf(stages: StagePart[], names: string[]): Row[] {
  const rows: Row[] = []
  for (const part of stages) {
    const stage = part.stage
    rows.push({
      key: `stage:${stage ?? ''}`,
      depth: 0,
      swatch: stageColour(names, stage),
      name: stage ?? 'no stage',
      location: null,
      share: part.fraction,
      score: part.score,
    })
    for (const process of part.processes) {
      rows.push({
        key: `process:${process.ref.code}`,
        depth: 1,
        swatch: null,
        name: process.name,
        location: process.location,
        share: process.fraction,
        score: process.score,
      })
      rows.push({
        key: `direct:${process.ref.code}`,
        depth: 2,
        swatch: null,
        name: 'direct',
        location: null,
        share: null,
        score: process.direct,
      })
      process.inputs.forEach((input, at) => rows.push(inputRow(input, `input:${process.ref.code}:${at}`)))
    }
  }
  return rows
}

function Part({ row }: { row: Row }) {
  return (
    <span className="inline-flex min-w-0 items-baseline gap-1.5 break-words" style={{ paddingLeft: row.depth * 16 }}>
      {row.swatch === null ? null : <span aria-hidden="true" className="size-2.5 shrink-0 self-center rounded-full" style={{ backgroundColor: row.swatch }} />}
      <span className={row.depth === 0 ? 'font-medium' : undefined}>{row.name}</span>
      {row.location === null ? null : <span className="text-xs text-muted-foreground">· {row.location}</span>}
    </span>
  )
}

export function StagesPage({ result }: { result: Result }) {
  const { id, params, system, impact, hash, root, stale, waiting, state, variant } = result
  const scores = impact.data?.value.scores ?? []
  const methods = impact.data?.value.methods ?? []
  const { chosen, choose } = useCategory(scores, id, (category) => category.value)
  const [cutoff, setCutoff] = useState(1)
  const split = useContributions(id, hash, { by: 'stage', method_id: chosen?.method_id, cutoff: cutoff / 100, demand: demandOf(params!, root), ...(variant !== null ? { variant } : {}) }, chosen !== undefined && !stale)
  const answer = split.data?.value
  const total = answer?.total
  const unit = total?.unit ?? chosen?.unit ?? ''
  const stages = answer?.stages ?? []
  const names = answer === undefined ? [] : stageNames(answer)
  const rows = rowsOf(stages, names)
  const columns: Column<Row>[] = [
    { key: 'share', header: 'Contribution', align: 'right', render: (row) => formatShare(row.share) },
    { key: 'part', header: 'Part', width: 'rest', render: (row) => <Part row={row} /> },
    { key: 'score', header: `Result${unit ? ` [${unit}]` : ''}`, align: 'right', render: (row) => formatAmount(row.score) },
  ]
  const summary: SummaryRow[] =
    total === undefined
      ? []
      : [{ key: 'total', className: 'font-medium', cells: { share: formatShare(total.value === 0 ? null : 1), part: 'Total', score: formatAmount(total.value) } }]
  return (
    <>
      <EditorHeader icon="result" page="By stage" entity={system?.name ?? ''} state={state} />
      <Section title="Stage contributions" sectionKey={`results:${id}:stages`} actions={<RequestAction systemId={id} entity="product_system" entityId={id} />}>
        <div className="flex flex-wrap items-center gap-3 pb-2 text-xs">
          <label className="flex min-w-0 max-w-full items-center gap-1">
            Impact category
            <select id="stages-category" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={chosen?.method_id ?? ''} onChange={(e) => choose(e.target.value)}>
              {scores.map((s) => (
                <option key={s.method_id} value={s.method_id}>
                  {categoryLabel(methodById(methods, s.method_id))}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            Don't show &lt; <input id="stages-cutoff" type="number" min="0" max="100" step="0.5" className="w-14 rounded-sm border bg-background px-1 text-right" value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} /> %
          </label>
        </div>
        {split.error ? <p className="text-destructive">{split.error.message}</p> : null}
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.key}
          rowClassName={(row) => (row.depth === 0 ? 'bg-chrome/60 font-medium' : '')}
          summary={summary}
          empty={split.data ? 'No stage holds a part of this score.' : (split.error?.message ?? waiting)}
        />
        <Hint of={split.data} />
      </Section>
    </>
  )
}
