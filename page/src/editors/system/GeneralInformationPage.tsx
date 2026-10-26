import { useLog, useValidation } from '@/api/queries'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { shortHash } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { CurrentValidationLine } from './CurrentValidationLine'
import type { SystemView } from './SystemEditor'

export function GeneralInformationPage({ view }: { view: SystemView }) {
  const { id, system } = view
  const log = useLog(id)
  const validation = useValidation(id, view.version === null)
  const last = log.data?.value.at(-1)
  const root = system.reference_process ? system.processes.find((p) => p.code === system.reference_process) : undefined
  const key = (s: string) => `system:${id}:${s}`
  return (
    <>
      <EditorHeader icon="system" page="General information" entity={system.name} />
      <Section title="General information" sectionKey={key('general')} actions={view.version ? undefined : <RequestAction systemId={id} entity="product_system" entityId={system.id} />}>
        <FieldGrid
          rows={[
            { label: 'Name', value: system.name },
            { label: 'Description', value: system.description },
            { label: 'Notes', value: system.notes },
            { label: 'Database', value: `${system.database.name} · ${system.database.scheme} ${system.database.version} · ${system.database.system_model}` },
            {
              label: '',
              value: (
                <span className="flex flex-wrap gap-4">
                  <span>
                    <b>Hash</b> {shortHash(view.version ?? system.hash)}
                  </span>
                  <span>
                    <b>Last change</b> {last ? `${last.timestamp} · ${last.actor.kind}${last.actor.name ? ` ${last.actor.name}` : ''} (${last.source})` : ''}
                  </span>
                  <span>
                    <b>UUID</b> {system.id}
                  </span>
                </span>
              ),
            },
          ]}
        />
      </Section>
      {view.version ? (
        <CurrentValidationLine id={id} />
      ) : (
        <Section title="Reference" sectionKey={key('reference')} actions={<RequestAction systemId={id} entity="product_system" entityId={system.id} />}>
          {validation.error ? <p className="text-destructive">{validation.error.message}</p> : null}
          {root ? null : <p className="text-warning">No reference process is set. The Statistics page names the case.</p>}
          {root ? (
            <FieldGrid
              rows={[
                {
                  label: 'Process',
                  value: (
                    <AppLink to={paths.process(id, root.code)} className="flex items-center gap-1.5 text-accent">
                      <Icon name="process" />
                      {root.name}
                    </AppLink>
                  ),
                },
                { label: 'Product', value: root.reference_product },
                { label: 'Unit', value: root.unit },
                { label: 'Target amount', value: '1.0' },
              ]}
            />
          ) : null}
          <Hint of={validation.data} />
        </Section>
      )}
      {view.openRequests > 0 ? (
        <Section title={`Open requests · ${view.openRequests}`} sectionKey={key('open')}>
          <AppLink to={paths.systemPage(id, 'requests')} className="text-accent">
            Open the Requests page
          </AppLink>
        </Section>
      ) : null}
    </>
  )
}
