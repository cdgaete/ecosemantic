import { useValidation } from '@/api/queries'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { countStatistics } from '@/lib/statistics'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { CurrentValidationLine } from './CurrentValidationLine'
import type { SystemView } from './SystemEditor'

export function StatisticsPage({ view }: { view: SystemView }) {
  const { id, system } = view
  const counts = countStatistics(system)
  const validation = useValidation(id, view.version === null)
  const report = validation.data?.value
  const root = system.reference_process ? system.processes.find((p) => p.code === system.reference_process) : undefined
  const action = view.version ? undefined : <RequestAction systemId={id} entity="product_system" entityId={system.id} />
  return (
    <>
      <EditorHeader icon="system" page="Statistics" entity={system.name} />
      <Section title="General statistics" sectionKey={`system:${id}:statistics`} actions={action}>
        <FieldGrid
          rows={[
            { label: 'Number of processes', value: String(counts.processes) },
            { label: 'Number of foreground links', value: String(counts.foregroundLinks) },
            { label: 'Number of background links', value: String(counts.backgroundLinks) },
            { label: 'Number of parameters', value: String(counts.parameters) },
            ...(view.version
              ? []
              : [
                  { label: 'Connected graph / can calculate?', value: report ? (report.is_valid ? 'Yes' : 'No') : validation.error ? validation.error.message : '…' },
                  { label: 'Reference process', value: root ? <AppLink to={paths.process(id, root.code)} className="text-accent">{root.name}</AppLink> : 'Not set' },
                ]),
          ]}
        />
      </Section>
      {view.version ? (
        <CurrentValidationLine id={id} />
      ) : (
        <Section title="Validation" sectionKey={`system:${id}:validation`} actions={action}>
          {report ? (
            <>
              <DataTable
                columns={[
                  { key: 'case', header: 'Case', render: (c) => c.id },
                  { key: 'passed', header: 'Result', render: (c) => (c.passed ? 'pass' : 'fail') },
                  { key: 'detail', header: 'Detail', render: (c) => c.detail ?? '' },
                ]}
                rows={report.cases}
                rowKey={(c) => c.id}
                rowClassName={(c) => (c.passed ? '' : 'text-destructive')}
              />
              {report.errors.length > 0 ? (
                <ul className="mt-2 list-disc pl-5">
                  {report.errors.map((e) => (
                    <li key={e.code} className="mb-1">
                      <div>
                        <b>{e.code}</b>: {e.message}
                      </div>
                      {e.process_codes.length > 0 ? <div className="text-muted-foreground">Processes: {e.process_codes.join(', ')}</div> : null}
                      <div className="text-muted-foreground">{e.suggestion}</div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : null}
          <Hint of={validation.data} />
        </Section>
      )}
    </>
  )
}
