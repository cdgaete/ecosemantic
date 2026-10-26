import { useContributions } from '@/api/queries'
import type { Hotspot, Process, ProductSystem } from '@/api/types'
import { categoryLabel, formatAgo, formatAmount, formatShare } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { BarChart } from './figures/BarChart'
import { demandOf, type ResultParams } from './params'
import { ranMonteCarlo } from './recorded'
import type { Result } from './ResultsEditor'

function targetOf(params: ResultParams, system: ProductSystem | undefined, rootProcess: Process | undefined): string {
  if (params.demand === undefined) return `${params.amount} ${rootProcess?.unit ?? ''}`
  return params.demand
    .map((item) => {
      const ref = item.ref
      if (ref.kind !== 'foreground') return `${item.amount} of ${ref.id}`
      const process = system?.processes.find((p) => p.code === ref.code)
      return `${item.amount} ${process?.unit ?? ''} of ${process?.reference_product ?? ref.code}`
    })
    .join(', ')
}

export function GeneralPage({ result }: { result: Result }) {
  const { id, params, hash, system, impact, root, stale, waiting } = result
  const first = impact.data?.value.scores[0]
  const top = useContributions(id, hash, { by: 'process', method_id: first?.method.id, top_n: 5, demand: demandOf(params!, root) }, first !== undefined && !stale)
  const rootProcess = system?.processes.find((p) => p.code === root)
  const action = <RequestAction systemId={id} entity="product_system" entityId={id} />
  const columns: Column<Hotspot>[] = [
    { key: 'process', header: 'Process', render: (h) => (h.location ? `${h.name} · ${h.location}` : h.name) },
    { key: 'result', header: 'Result', align: 'right', render: (h) => formatAmount(h.score) },
    { key: 'unit', header: 'Unit', render: () => first?.unit ?? '' },
    { key: 'share', header: 'Contribution', align: 'right', render: (h) => formatShare(h.fraction) },
  ]
  return (
    <>
      <EditorHeader icon="result" page="General information" entity={system?.name ?? ''} />
      <Section title="General information" sectionKey={`results:${id}:general`} actions={action}>
        <FieldGrid
          rows={[
            { label: 'Product system', value: system?.name ?? '' },
            { label: 'Reference process', value: rootProcess?.name ?? (root ?? '') },
            { label: 'Target amount', value: targetOf(params!, system, rootProcess) },
            { label: 'Impact assessment method', value: params?.impact_method ?? first?.method.spec ?? '' },
            { label: 'Parameter set', value: params?.variants.length ? params.variants.join(', ') : 'base' },
            ...(result.call ? [{ label: 'Calculated by', value: `${result.call.origin === 'view' ? 'you' : result.call.agent}, ${formatAgo(result.call.started_at)}` }] : []),
          ]}
        />
        {result.call && ranMonteCarlo(result.call) ? <p className="pt-2 text-xs text-muted-foreground">This call also ran a Monte Carlo simulation; this page shows its deterministic result.</p> : null}
      </Section>
      <Section title="Top 5 direct contributions to impact category results - overview" sectionKey={`results:${id}:top5`} actions={action}>
        {first && top.data ? (
          <>
            <BarChart rows={(top.data.value.processes ?? []).map((h) => ({ label: h.location ? `${h.name} · ${h.location}` : h.name, value: h.score, share: h.fraction }))} unit={first.unit} />
            <div className="pt-3">
              <DataTable columns={columns} rows={top.data.value.processes ?? []} rowKey={(h) => `${h.rank}`} />
              <Hint of={top.data} />
            </div>
          </>
        ) : (
          <p className="text-muted-foreground">{top.error?.message ?? impact.error?.message ?? waiting}</p>
        )}
        {first ? <p className="pt-1 text-xs text-muted-foreground">{categoryLabel(first.method)}</p> : null}
      </Section>
    </>
  )
}
