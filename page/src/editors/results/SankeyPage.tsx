import { useMemo, useState } from 'react'
import { useContributions } from '@/api/queries'
import { useCategory } from '@/lib/address'
import { categoryLabel, formatAmount, formatShare, methodById } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { Sankey } from './figures/Sankey'
import { sankeyFromTree, type SankeyNodeDatum } from './figures/sankey'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

export function SankeyPage({ result }: { result: Result }) {
  const { id, params, system, impact, hash, root, stale, waiting } = result
  const scores = impact.data?.value.scores ?? []
  const methods = impact.data?.value.methods ?? []
  const [share, setShare] = useState(1)
  const [maxNodes, setMaxNodes] = useState(10)
  const { chosen, choose } = useCategory(scores)
  const chosenMethod = chosen === undefined ? undefined : methodById(methods, chosen.method_id)
  const tree = useContributions(id, hash, { by: 'path', method_id: chosen?.method_id, max_level: 6, max_nodes: maxNodes, cutoff: share / 100, demand: demandOf(params!, root) }, chosen !== undefined && !stale)
  const figure = useMemo(() => (tree.data?.value.root ? sankeyFromTree(tree.data.value.root) : null), [tree.data])
  const unit = tree.data?.value.total.unit ?? ''
  const action = <RequestAction systemId={id} entity="product_system" entityId={id} />
  const columns: Column<SankeyNodeDatum>[] = [
    { key: 'process', header: 'Process', render: (n) => (n.location ? `${n.name} · ${n.location}` : n.name) },
    { key: 'share', header: 'Upstream total', align: 'right', render: (n) => formatShare(n.fraction) },
    { key: 'score', header: `Score${unit ? ` [${unit}]` : ''}`, align: 'right', render: (n) => formatAmount(n.score) },
  ]
  return (
    <>
      <EditorHeader icon="result" page="Sankey diagram" entity={system?.name ?? ''} />
      <div className="grid grid-cols-1 gap-x-6 gap-y-1 border-b px-4 py-1 text-xs @lg:grid-cols-3">
        <span>
          <b>{system?.name}</b>
          <br />
          {chosenMethod?.impact_method}
        </span>
        <label className="flex min-w-0 max-w-full flex-col gap-1">
          Impact category:
          <select id="sankey-category" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={chosen?.method_id ?? ''} onChange={(e) => choose(e.target.value)}>
            {scores.map((s) => (
              <option key={s.method_id} value={s.method_id}>
                {categoryLabel(methodById(methods, s.method_id))}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-1">
            Min. contribution share:
            <input id="sankey-share" type="number" min="0" max="100" step="0.1" className="w-14 rounded-sm border bg-background px-1 text-right" value={share} onChange={(e) => setShare(Number(e.target.value))} /> %
          </label>
          <label className="flex items-center gap-1">
            Max. number of processes:
            <input id="sankey-nodes" type="number" min="1" max="200" className="w-14 rounded-sm border bg-background px-1 text-right" value={maxNodes} onChange={(e) => setMaxNodes(Number(e.target.value))} />
          </label>
        </div>
      </div>
      <Section title="Sankey diagram" sectionKey={`results:${id}:sankey`} actions={action}>
        {tree.error ? <p className="text-destructive">{tree.error.message}</p> : null}
        {figure ? <Sankey nodes={figure.nodes} links={figure.links} unit={unit} title={chosenMethod ? categoryLabel(chosenMethod) : ''} /> : !tree.error ? <p className="text-muted-foreground">{waiting}</p> : null}
      </Section>
      {figure ? (
        <Section title="Sankey nodes" sectionKey={`results:${id}:sankey-nodes`} actions={action}>
          <DataTable columns={columns} rows={figure.nodes} rowKey={(n) => n.id} />
          <Hint of={tree.data} />
        </Section>
      ) : null}
    </>
  )
}
