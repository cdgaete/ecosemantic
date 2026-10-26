import { Fragment, useState } from 'react'
import { useContributions } from '@/api/queries'
import type { Score } from '@/api/types'
import { formatAmount, formatShare } from '@/lib/format'
import { cn } from '@/lib/utils'
import { RequestAction } from '@/requests/RequestAction'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

function signed(delta: number): string {
  return `${delta >= 0 ? '+' : '−'}${formatAmount(Math.abs(delta))}`
}

function Children({ result, score, by, cutoff }: { result: Result; score: Score; by: 'process' | 'flow'; cutoff: number }) {
  const parts = useContributions(result.id, result.hash, { by, method_id: score.method.id, top_n: 20, demand: demandOf(result.params!, result.root) }, !result.stale)
  if (parts.error) return <tr><td colSpan={99} className="px-2 text-destructive">{parts.error.message}</td></tr>
  if (!parts.data) return <tr><td colSpan={99} className="px-2 text-muted-foreground">{result.waiting}</td></tr>
  const rows = by === 'process' ? (parts.data.value.processes ?? []).map((h) => ({ key: `${h.ref.kind === 'background' ? h.ref.id : h.ref.code}`, icon: h.ref.kind === 'foreground' ? ('process' as const) : ('product' as const), name: h.location ? `${h.name} · ${h.location}` : h.name, share: h.fraction, score: h.score })) : (parts.data.value.flows ?? []).map((f) => ({ key: f.flow.id, icon: 'elementary' as const, name: `${f.name} (${f.compartment})`, share: f.fraction, score: f.score }))
  return (
    <>
      {parts.data.hint ? (
        <tr>
          <td colSpan={99} className="px-2 pl-7 text-xs text-muted-foreground">
            {parts.data.hint}
          </td>
        </tr>
      ) : null}
      {rows.filter((r) => 100 * Math.abs(r.share) >= cutoff).map((r) => (
        <tr key={r.key}>
          <td className="border-r border-b py-0.5 pl-7 pr-2 break-words">
            <span className="flex flex-wrap items-center gap-1">
              <Icon name={r.icon} />
              {r.name}
              <span className="text-muted-foreground @lg:hidden">· {formatShare(r.share)}</span>
            </span>
          </td>
          <td className="hidden border-r border-b px-2 text-muted-foreground @lg:table-cell">{formatShare(r.share)}</td>
          <td className="border-r border-b px-2 text-right tabular-nums">{formatAmount(r.score)}</td>
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
  const { id, params, system, impact } = result
  const [by, setBy] = useState<'process' | 'flow'>('process')
  const [cutoff, setCutoff] = useState(1)
  const [open, setOpen] = useState<string[]>([])
  const value = impact.data?.value
  const title = params?.impact_method ?? value?.scores[0]?.method.impact_method ?? ''
  return (
    <>
      <EditorHeader icon="result" page="Impact analysis" entity={system?.name ?? ''} />
      <Section title={`Impact analysis: ${title}`} sectionKey={`results:${id}:impact`} actions={<RequestAction systemId={id} entity="product_system" entityId={id} />}>
        <div className="flex flex-wrap items-center gap-3 pb-2 text-xs">
          <span>Sub-group by:</span>
          <label className="flex items-center gap-1">
            <input type="radio" name="by" checked={by === 'process'} onChange={() => setBy('process')} /> Processes
          </label>
          <label className="flex items-center gap-1">
            <input type="radio" name="by" checked={by === 'flow'} onChange={() => setBy('flow')} /> Flows
          </label>
          <span className="text-muted-foreground">|</span>
          <label className="flex items-center gap-1">
            Don't show &lt; <input id="impact-cutoff" type="number" min="0" max="100" step="0.5" className="w-14 rounded-sm border bg-background px-1 text-right" value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} /> %
          </label>
          {params?.variants.length ? <span className="text-muted-foreground">| Variants: {params.variants.join(', ')}</span> : null}
        </div>
        {!value ? <p className="text-muted-foreground">{impact.error?.message ?? result.waiting}</p> : null}
        {value ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border text-[12.5px]">
              <thead>
                <tr>
                  {[
                    { text: 'Name', right: false, wide: false },
                    { text: 'Category', right: false, wide: true },
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
                {value.scores.map((score, i) => (
                  <Fragment key={score.method.id}>
                    <tr className={open.includes(score.method.id) ? 'bg-selected' : ''}>
                      <td className="border-r border-b px-2 py-0.5 break-words">
                        <button type="button" className="mr-1 text-muted-foreground" aria-label="Expand" onClick={() => setOpen(open.includes(score.method.id) ? open.filter((o) => o !== score.method.id) : [...open, score.method.id])}>
                          {open.includes(score.method.id) ? '▾' : '▸'}
                        </button>
                        <Icon name="result" /> {score.method.impact_category}
                        {value.variants.map((variant) => (
                          <span key={variant.name} className="block text-xs text-muted-foreground @lg:hidden">
                            {variant.name}: {formatAmount(variant.scores[i].value)} ({signed(variant.deltas[i])})
                          </span>
                        ))}
                      </td>
                      <td className="hidden border-r border-b px-2 @lg:table-cell">
                        {[score.method.impact_method, score.method.indicator].filter(Boolean).join(' · ')}
                      </td>
                      <td className="border-r border-b px-2 text-right tabular-nums">{formatAmount(score.value)}</td>
                      <td className="border-r border-b px-2">{score.unit}</td>
                      {value.variants.map((variant) => (
                        <td key={variant.name} className="hidden border-r border-b px-2 text-right tabular-nums @lg:table-cell">
                          {formatAmount(variant.scores[i].value)} ({signed(variant.deltas[i])})
                        </td>
                      ))}
                    </tr>
                    {open.includes(score.method.id) ? <Children result={result} score={score} by={by} cutoff={cutoff} /> : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <Hint of={impact.data} />
      </Section>
    </>
  )
}
