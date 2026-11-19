import type { Process } from '@/api/types'
import { RequestAction } from '@/requests/RequestAction'
import { MACHINE } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Section } from '@/window/Section'
import type { CanvasVariant } from '@/window/useCanvasState'

const NAMED = ['life_cycle_stage', 'hierarchy_level', 'supply_chain_tier']

export function ProcessGeneralPage({ systemId, process, state }: { systemId: string; process: Process; state: CanvasVariant | null }) {
  const extra = Object.entries(process.metadata).filter(([k]) => !NAMED.includes(k))
  const key = (s: string) => `process:${systemId}:${process.code}:${s}`
  return (
    <>
      <EditorHeader icon="process" page="General information" entity={process.name} state={state} />
      <Section title="General information" sectionKey={key('general')} actions={<RequestAction systemId={systemId} entity="process" entityId={process.code} />}>
        <FieldGrid
          rows={[
            { label: 'Name', value: process.name },
            { label: 'Code', value: <span className={MACHINE}>{process.code}</span> },
            { label: 'Reference product', value: process.reference_product },
            { label: 'Unit', value: process.unit },
            { label: 'Location', value: process.location },
            { label: 'Comment', value: process.comment ?? '' },
          ]}
        />
      </Section>
      <Section title="Metadata" sectionKey={key('metadata')} actions={<RequestAction systemId={systemId} entity="process" entityId={process.code} />}>
        <FieldGrid
          rows={[
            { label: 'Life-cycle stage', value: String(process.metadata['life_cycle_stage'] ?? '') },
            { label: 'Hierarchy level', value: String(process.metadata['hierarchy_level'] ?? '') },
            { label: 'Supply-chain tier', value: String(process.metadata['supply_chain_tier'] ?? '') },
            ...extra.map(([k, v]) => ({ label: k, value: JSON.stringify(v) })),
          ]}
        />
      </Section>
    </>
  )
}
