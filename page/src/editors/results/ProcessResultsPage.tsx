import { useState } from 'react'
import { useContributions } from '@/api/queries'
import { useCategory } from '@/lib/address'
import type { Hotspot } from '@/api/types'
import { categoryLabel, formatAmount, formatShare } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

export function ProcessResultsPage({ result }: { result: Result }) {
  const { id, params, system, impact } = result
  const scores = impact.data?.value.scores ?? []
  const { chosen, choose } = useCategory(scores)
  const [cutoff, setCutoff] = useState(1)
  const parts = useContributions(id, result.hash, { by: 'process', method_id: chosen?.method.id, top_n: 50, demand: demandOf(params!, result.root) }, chosen !== undefined && !result.stale)
  const columns: Column<Hotspot>[] = [
    { key: 'share', header: 'Contribution', align: 'right', render: (h) => formatShare(h.fraction) },
    { key: 'process', header: 'Process', render: (h) => h.name },
    { key: 'location', header: 'Location', render: (h) => h.location ?? '' },
    { key: 'product', header: 'Reference product', render: (h) => h.reference_product },
    { key: 'score', header: `Result${chosen ? ` [${chosen.unit}]` : ''}`, align: 'right', render: (h) => formatAmount(h.score) },
  ]
  return (
    <>
      <EditorHeader icon="result" page="Process results" entity={system?.name ?? ''} />
      <Section title="Process contributions" sectionKey={`results:${id}:processes`} actions={<RequestAction systemId={id} entity="product_system" entityId={id} />}>
        <div className="flex flex-wrap items-center gap-3 pb-2 text-xs">
          <label className="flex min-w-0 max-w-full items-center gap-1">
            Impact category
            <select id="processes-category" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={chosen?.method.id ?? ''} onChange={(e) => choose(e.target.value)}>
              {scores.map((s) => (
                <option key={s.method.id} value={s.method.id}>
                  {categoryLabel(s.method)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            Don't show &lt; <input id="processes-cutoff" type="number" min="0" max="100" step="0.5" className="w-14 rounded-sm border bg-background px-1 text-right" value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} /> %
          </label>
        </div>
        <DataTable columns={columns} rows={(parts.data?.value.processes ?? []).filter((h) => 100 * Math.abs(h.fraction) >= cutoff)} rowKey={(h) => `${h.rank}`} empty={parts.data ? 'No process above the cut-off.' : (parts.error?.message ?? result.waiting)} />
        <Hint of={parts.data} />
      </Section>
    </>
  )
}
