import type { Json, Process } from '@/api/types'
import { RequestAction } from '@/requests/RequestAction'
import { MACHINE } from '@/window/DataTable'
import { FieldGrid } from '@/window/FieldGrid'
import { Section } from '@/window/Section'

const NAMED = ['life_cycle_stage', 'hierarchy_level', 'supply_chain_tier']

function metadataText(value: Json | undefined): string | null {
  if (value === null || value === undefined) return null
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

export function ProcessGeneralPage({ systemId, process }: { systemId: string; process: Process }) {
  const extra = Object.entries(process.metadata).filter(([k]) => !NAMED.includes(k))
  const key = (s: string) => `process:${systemId}:${process.code}:${s}`
  return (
    <>
      <Section title="General information" sectionKey={key('general')} actions={<RequestAction systemId={systemId} entity="process" entityId={process.code} />}>
        <FieldGrid
          rows={[
            { label: 'Name', value: process.name },
            { label: 'Code', value: <span className={MACHINE}>{process.code}</span> },
            { label: 'Reference product', value: process.reference_product },
            { label: 'Unit', value: process.unit },
            { label: 'Location', value: process.location },
            { label: 'Comment', value: process.comment, empty: 'No comment provided' },
          ]}
        />
      </Section>
      <Section title="Metadata" sectionKey={key('metadata')} actions={<RequestAction systemId={systemId} entity="process" entityId={process.code} />}>
        <FieldGrid
          empty="No metadata provided"
          rows={[
            { label: 'Life-cycle stage', value: metadataText(process.metadata['life_cycle_stage']) },
            { label: 'Hierarchy level', value: metadataText(process.metadata['hierarchy_level']) },
            { label: 'Supply-chain tier', value: metadataText(process.metadata['supply_chain_tier']) },
            ...extra.map(([k, v]) => ({ label: k, value: metadataText(v) })),
          ]}
        />
      </Section>
    </>
  )
}
