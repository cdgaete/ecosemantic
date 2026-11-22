import { Fragment, useState } from 'react'
import { useContributions } from '@/api/queries'
import type { Score, Total, VariantScores } from '@/api/types'
import { cutNotice, formatAmount, formatShare, formatUnit, indicatorLabel, methodById, weightingSetName } from '@/lib/format'
import { cn } from '@/lib/utils'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, NUMERIC, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

function signed(delta: number): string {
  return `${delta >= 0 ? '+' : '−'}${formatAmount(Math.abs(delta))}`
}

interface TotalRow {
  total: Total
  variants: ({ total: Total; delta: number | null } | null)[]
}

function Totals({ totals, variants, sectionKey }: { totals: Total[]; variants: VariantScores[]; sectionKey: string }) {
  const columns: Column<TotalRow>[] = [
    { key: 'set', header: 'Name', width: 'rest', render: (row) => weightingSetName(row.total) },
    { key: 'value', header: 'Total', align: 'right', render: (row) => (row.total.value === null ? row.total.reason : formatAmount(row.total.value)) },
    { key: 'unit', header: 'Unit', render: (row) => formatUnit(row.total.unit) },
    ...variants.map((variant, i) => ({
      key: `variant:${variant.name}`,
      header: `${variant.name} (Δ)`,
      align: 'right' as const,
      folds: true,
      render: (row: TotalRow) => {
        const moved = row.variants[i]
        if (moved === null || moved.total.value === null || moved.delta === null) return null
        return `${formatAmount(moved.total.value)} (${signed(moved.delta)})`
      },
    })),
  ]
  const rows: TotalRow[] = totals.map((total) => ({
    total,
    variants: variants.map((variant) => {
      const at = variant.totals.findIndex((moved) => moved.position === total.position)
      return at < 0 ? null : { total: variant.totals[at], delta: variant.total_deltas[at] }
    }),
  }))
  return (
    <Section title="Totals" sectionKey={sectionKey}>
      <DataTable columns={columns} rows={rows} rowKey={(row) => `total:${row.total.position}`} />
      <p className="pt-1 text-xs text-muted-foreground">{totals[0].value_choices}</p>
    </Section>
  )
}

function Children({ result, score, by, cutoff, byMethod, byIndicator }: { result: Result; score: Score; by: 'process' | 'flow'; cutoff: number; byMethod: boolean; byIndicator: boolean }) {
  const parts = useContributions(result.id, result.hash, { by, method_id: score.method_id, top_n: 20, cutoff: cutoff / 100, demand: demandOf(result.params!, result.root), ...(result.variant !== null ? { variant: result.variant } : {}) }, !result.stale)
  if (parts.error) return <tr><td colSpan={99} className="px-2 text-destructive">{parts.error.message}</td></tr>
  if (!parts.data) return <tr><td colSpan={99} className="px-2 text-muted-foreground">{result.waiting}</td></tr>
  const rows = by === 'process' ? (parts.data.value.processes ?? []).map((h) => ({ key: `${h.ref.kind === 'background' ? h.ref.id : h.ref.code}`, icon: h.ref.kind === 'foreground' ? ('process' as const) : ('product' as const), name: h.location ? `${h.name} · ${h.location}` : h.name, share: h.fraction, score: h.score })) : (parts.data.value.flows ?? []).map((f) => ({ key: f.flow.id, icon: 'elementary' as const, name: `${f.name} (${f.sub_compartment ? `${f.compartment} / ${f.sub_compartment}` : f.compartment})`, share: f.fraction, score: f.score }))
  const cut = cutNotice(parts.data.value.cut)
  return (
    <>
      {parts.data.hint ? (
        <tr>
          <td colSpan={99} className="px-2 pl-7 text-xs text-muted-foreground">
            {parts.data.hint}
          </td>
        </tr>
      ) : null}
      {cut ? (
        <tr>
          <td colSpan={99} className="px-2 pl-7 text-xs text-muted-foreground">
            {cut}
          </td>
        </tr>
      ) : null}
      {rows.map((r) => (
        <tr key={r.key}>
          <td className="border-r border-b py-0.5 pl-7 pr-2 break-words">
            <span className="flex flex-wrap items-center gap-1">
              <Icon name={r.icon} />
              {r.name}
              <span className="text-muted-foreground">· {formatShare(r.share)}</span>
            </span>
          </td>
          {byMethod ? <td className="hidden border-r border-b @lg:table-cell" /> : null}
          {byIndicator ? <td className="hidden border-r border-b @lg:table-cell" /> : null}
          <td className={cn('border-r border-b px-2 text-right', NUMERIC)}>{formatAmount(r.score)}</td>
          <td className="border-r border-b px-2">{score.unit}</td>
          {result.params?.variants.map((v) => (
            <td key={v} className="hidden border-r border-b @lg:table-cell" />
          ))}
        </tr>
      ))}
    </>
  )
}

export function ImpactPage({ result }: { result: Result }) {
  const { id, params, system, impact, state } = result
  const [by, setBy] = useState<'process' | 'flow'>('process')
  const [cutoff, setCutoff] = useState(1)
  const [open, setOpen] = useState<string[]>([])
  const value = impact.data?.value
  const methods = value?.methods ?? []
  const scores = value?.scores ?? []
  const first = value?.scores[0]
  const title = params?.impact_method ?? (first === undefined ? '' : methodById(methods, first.method_id).impact_method)
  const byMethod = new Set(scores.map((score) => methodById(methods, score.method_id).impact_method)).size > 1
  const byIndicator = scores.some((score) => indicatorLabel(methodById(methods, score.method_id)) !== '')
  return (
    <>
      <EditorHeader icon="result" page="Impact analysis" entity={system?.name ?? ''} state={state} />
      <Section title={`Impact analysis: ${title}`} sectionKey={`results:${id}:impact`} actions={<RequestAction systemId={id} entity="product_system" entityId={id} />}>
        <div className="flex flex-wrap items-center gap-3 pb-2 text-xs">
          <span>Sub-group by:</span>
          <label className="flex items-center gap-1">
            <input type="radio" name="by" checked={by === 'process'} onChange={() => setBy('process')} /> Processes
          </label>
          <label className="flex items-center gap-1">
            <input type="radio" name="by" checked={by === 'flow'} onChange={() => setBy('flow')} /> Flows
          </label>
          <label className="flex items-center gap-1">
            Don't show &lt; <input id="impact-cutoff" type="number" min="0" max="100" step="0.5" className="w-14 rounded-sm border bg-background px-1 text-right" value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} /> %
          </label>
          {params?.variants.length ? (
            <span className="flex flex-wrap items-center gap-2 text-muted-foreground">
              <span>Variants:</span>
              {params.variants.map((variant) => (
                <span key={variant}>{variant}</span>
              ))}
            </span>
          ) : null}
        </div>
        {!value && !impact.error ? <p className="text-muted-foreground">{result.waiting}</p> : null}
        {value ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border text-[12.5px]">
              <thead>
                <tr>
                  {[
                    { text: 'Name', right: false, wide: false },
                    ...(byMethod ? [{ text: 'Method', right: false, wide: true }] : []),
                    ...(byIndicator ? [{ text: 'Indicator', right: false, wide: true }] : []),
                    { text: 'Impact assessment result', right: true, wide: false },
                    { text: 'Unit', right: false, wide: false },
                    ...(params?.variants ?? []).map((v) => ({ text: `${v} (Δ)`, right: true, wide: true })),
                  ].map((h) => (
                    <th key={h.text} className={cn('border-r border-b bg-chrome px-2 py-1 font-normal', h.right ? 'text-right' : 'text-left', h.wide && 'hidden @lg:table-cell')}>
                      {h.text}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {value.scores.map((score, i) => {
                  const method = methodById(value.methods, score.method_id)
                  return (
                    <Fragment key={score.method_id}>
                      <tr className={open.includes(score.method_id) ? 'bg-selected' : ''}>
                        <td className="border-r border-b px-2 py-0.5 break-words">
                          <button type="button" className="mr-1 text-muted-foreground" aria-label="Expand" onClick={() => setOpen(open.includes(score.method_id) ? open.filter((o) => o !== score.method_id) : [...open, score.method_id])}>
                            {open.includes(score.method_id) ? '▾' : '▸'}
                          </button>
                          <Icon name="result" /> {method.impact_category}
                          {byMethod ? (
                            <span className="block text-xs @lg:hidden">
                              <span className="text-muted-foreground">Method:</span> {method.impact_method}
                            </span>
                          ) : null}
                          {byIndicator ? (
                            <span className="block text-xs @lg:hidden">
                              <span className="text-muted-foreground">Indicator:</span> {indicatorLabel(method)}
                            </span>
                          ) : null}
                          {value.variants.map((variant) => (
                            <span key={variant.name} className="block text-xs text-muted-foreground @lg:hidden">
                              {variant.name}: {formatAmount(variant.scores[i].value)} ({signed(variant.deltas[i])})
                            </span>
                          ))}
                        </td>
                        {byMethod ? (
                          <td className="hidden border-r border-b px-2 @lg:table-cell">{method.impact_method}</td>
                        ) : null}
                        {byIndicator ? (
                          <td className="hidden border-r border-b px-2 @lg:table-cell">{indicatorLabel(method)}</td>
                        ) : null}
                        <td className={cn('border-r border-b px-2 text-right', NUMERIC)}>{formatAmount(score.value)}</td>
                        <td className="border-r border-b px-2">{score.unit}</td>
                        {value.variants.map((variant) => (
                          <td key={variant.name} className={cn('hidden border-r border-b px-2 text-right @lg:table-cell', NUMERIC)}>
                            {formatAmount(variant.scores[i].value)} ({signed(variant.deltas[i])})
                          </td>
                        ))}
                      </tr>
                      {open.includes(score.method_id) ? (
                        <Children result={result} score={score} by={by} cutoff={cutoff} byMethod={byMethod} byIndicator={byIndicator} />
                      ) : null}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
        <Hint of={impact.data} />
      </Section>
      {value !== undefined && value.totals.length > 0 ? <Totals totals={value.totals} variants={value.variants} sectionKey={`results:${id}:totals`} /> : null}
    </>
  )
}
