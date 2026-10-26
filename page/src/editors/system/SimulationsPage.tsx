import { useRuns } from '@/api/queries'
import type { Run } from '@/api/types'
import { formatAmount, shortHash } from '@/lib/format'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import type { SystemView } from './SystemEditor'

export function SimulationsPage({ view }: { view: SystemView }) {
  const runs = useRuns(view.id)
  const columns: Column<Run>[] = [
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <AppLink to={paths.simulation(view.id, r.id)} className="underline">
          {r.status}
        </AppLink>
      ),
    },
    { key: 'iterations', header: 'Iterations', align: 'right', render: (r) => String(r.progress.iterations) },
    { key: 'worst', header: 'Worst median relative SE', align: 'right', render: (r) => (r.progress.worst_rel_se === null ? '–' : formatAmount(r.progress.worst_rel_se)) },
    { key: 'method', header: 'Impact method', render: (r) => r.methods[0]?.impact_method ?? '' },
    { key: 'posted', header: 'Posted', render: (r) => r.posted_at },
    { key: 'finished', header: 'Finished', render: (r) => r.finished_at ?? '–' },
    { key: 'hash', header: 'Computed on', render: (r) => (r.at_hash === view.system.hash ? shortHash(r.at_hash) : `${shortHash(r.at_hash)} (an earlier state)`) },
  ]
  return (
    <>
      <EditorHeader icon="simulation" page="Simulations" entity={view.system.name} />
      <Section title="Simulations" sectionKey={`system:${view.id}:simulations`} actions={<RequestAction systemId={view.id} entity="product_system" entityId={view.system.id} />}>
        {runs.error ? <p className="text-destructive">{runs.error.message}</p> : null}
        <DataTable
          columns={columns}
          rows={runs.data?.value ?? []}
          rowKey={(r) => r.id}
          empty={
            <>
              No simulation yet. Start one from Calculate ▸{' '}
              <AppLink to={paths.results(view.id, 'setup', '?kind=simulation')} className="text-primary hover:underline">
                Monte Carlo simulation…
              </AppLink>
            </>
          }
        />
      </Section>
    </>
  )
}
