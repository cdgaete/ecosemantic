import { useState } from 'react'
import { useContributions } from '@/api/queries'
import { useCategory } from '@/lib/address'
import type { TreeNode } from '@/api/types'
import { categoryLabel, formatAmount, formatShare, methodById } from '@/lib/format'
import { cn } from '@/lib/utils'
import { RequestAction } from '@/requests/RequestAction'
import { EditorHeader } from '@/window/EditorHeader'
import { NUMERIC } from '@/window/DataTable'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

function Rows({ node, depth, unit, open, toggle, id }: { node: TreeNode; depth: number; unit: string; open: Set<string>; toggle: (id: string) => void; id: string }) {
  const children = node.children.filter((c) => c.kind !== 'elementary_flow')
  const expanded = open.has(id)
  return (
    <>
      <tr>
        <td className={cn('border-r border-b px-2 py-0.5 text-right', NUMERIC)}>{formatShare(node.fraction)}</td>
        <td className="border-r border-b py-0.5 pr-2 break-words" style={{ paddingLeft: 8 + depth * 16 }}>
          {children.length > 0 ? (
            <button type="button" className="mr-1 text-muted-foreground" aria-label="Expand" aria-expanded={expanded} onClick={() => toggle(id)}>
              {expanded ? '▾' : '▸'}
            </button>
          ) : (
            <span className="mr-1 inline-block w-3" />
          )}
          {node.kind === 'remainder' ? (
            <i className="text-muted-foreground">rest</i>
          ) : (
            <span className="inline-flex min-w-0 items-center gap-1">
              <Icon name={node.ref?.kind === 'foreground' ? 'process' : 'product'} />
              {node.name}
              {node.location ? <span className="text-muted-foreground">· {node.location}</span> : null}
            </span>
          )}
          <span className="block text-xs @lg:hidden">
            <span className="text-muted-foreground">Total result:</span> <span className={NUMERIC}>{formatAmount(node.score)}</span> {unit}
          </span>
        </td>
        <td className={cn('hidden border-r border-b px-2 text-right @lg:table-cell', NUMERIC)}>{formatAmount(node.score)}</td>
        <td className="hidden border-r border-b px-2 @lg:table-cell">{unit}</td>
      </tr>
      {expanded ? children.map((child, i) => <Rows key={`${id}/${i}`} node={child} depth={depth + 1} unit={unit} open={open} toggle={toggle} id={`${id}/${i}`} />) : null}
    </>
  )
}

export function ContributionTreePage({ result }: { result: Result }) {
  const { id, params, system, impact, hash, root, stale, waiting, state, variant } = result
  const scores = impact.data?.value.scores ?? []
  const methods = impact.data?.value.methods ?? []
  const [maxLevel, setMaxLevel] = useState(3)
  const [maxNodes, setMaxNodes] = useState(50)
  const [cutoff, setCutoff] = useState(0.1)
  const [open, setOpen] = useState<Set<string>>(new Set(['root']))
  const { chosen, choose } = useCategory(scores, id, (category) => category.value)
  const tree = useContributions(id, hash, { by: 'path', method_id: chosen?.method_id, max_level: maxLevel, max_nodes: maxNodes, cutoff: cutoff / 100, demand: demandOf(params!, root), ...(variant !== null ? { variant } : {}) }, chosen !== undefined && !stale)
  const toggle = (key: string) =>
    setOpen((s) => {
      const next = new Set(s)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  return (
    <>
      <EditorHeader icon="result" page="Contribution tree" entity={system?.name ?? ''} state={state} />
      <Section title="Contribution tree" sectionKey={`results:${id}:tree`} actions={<RequestAction systemId={id} entity="product_system" entityId={id} />}>
        <div className="flex flex-wrap items-center gap-3 pb-2 text-xs">
          <label className="flex min-w-0 max-w-full items-center gap-1">
            Impact category
            <select id="tree-category" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={chosen?.method_id ?? ''} onChange={(e) => choose(e.target.value)}>
              {scores.map((s) => (
                <option key={s.method_id} value={s.method_id}>
                  {categoryLabel(methodById(methods, s.method_id))}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            Max. number of levels
            <input id="tree-depth" type="number" min="1" max="10" className="w-12 rounded-sm border bg-background px-1 text-right" value={maxLevel} onChange={(e) => setMaxLevel(Number(e.target.value))} />
          </label>
          <label className="flex items-center gap-1">
            Max. nodes
            <input id="tree-nodes" type="number" min="1" max="500" className="w-14 rounded-sm border bg-background px-1 text-right" value={maxNodes} onChange={(e) => setMaxNodes(Number(e.target.value))} />
          </label>
          <label className="flex items-center gap-1">
            Min. contribution %
            <input id="tree-cutoff" type="number" min="0" max="100" step="0.1" className="w-14 rounded-sm border bg-background px-1 text-right" value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} />
          </label>
        </div>
        {tree.error ? <p className="text-destructive">{tree.error.message}</p> : null}
        {tree.data?.value.root ? (
          <>
            <table className="w-full border-collapse border text-[12.5px]">
              <thead>
                <tr>
                  <th className="border-r border-b bg-chrome px-2 py-1 text-right font-normal">Contribution</th>
                  <th className="border-r border-b bg-chrome px-2 py-1 text-left font-normal">Process</th>
                  <th className="hidden border-r border-b bg-chrome px-2 py-1 text-right font-normal @lg:table-cell">Total result</th>
                  <th className="hidden border-r border-b bg-chrome px-2 py-1 text-left font-normal @lg:table-cell">Unit</th>
                </tr>
              </thead>
              <tbody>
                <Rows node={tree.data.value.root} depth={0} unit={tree.data.value.total.unit} open={open} toggle={toggle} id="root" />
              </tbody>
            </table>
            {tree.data.value.truncated ? <p className="pt-1 text-xs text-muted-foreground">Truncated at the depth and node limit above.</p> : null}
            <Hint of={tree.data} />
          </>
        ) : !tree.error ? (
          <p className="text-muted-foreground">{waiting}</p>
        ) : null}
      </Section>
    </>
  )
}
