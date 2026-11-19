import type { ReactNode } from 'react'
import { useElementaryFlow } from '@/api/queries'
import { MACHINE } from '@/window/DataTable'
import { Section } from '@/window/Section'
import { DetailHeader } from './DetailHeader'
import { Facts } from './Facts'

export function FlowDetail({ name, item }: { name: string; item: string }) {
  const read = useElementaryFlow(name, item)
  if (read.error) return <p className="min-w-0 text-destructive">{read.error.message}</p>
  const flow = read.data?.value
  if (flow === undefined) return <p className="min-w-0 text-muted-foreground">Loading…</p>
  const rows: [string, ReactNode][] = [
    ['Compartment', flow.compartment],
    ['Sub-compartment', flow.sub_compartment ?? ''],
    ['Unit', flow.unit],
    ['Side', flow.side],
    ['Flow type', flow.flow_type],
    ['CAS number', flow.cas_number === null ? '' : <span className={MACHINE}>{flow.cas_number}</span>],
  ]
  if (flow.cas_number === null && flow.cas_as_published !== null) {
    rows.push(['CAS as published', <span className={MACHINE}>{flow.cas_as_published}</span>])
  }
  return (
    <section aria-label={flow.name} className="flex min-w-0 flex-col">
      <DetailHeader title={flow.name} />
      <Facts rows={rows} />
      {flow.synonyms.length === 0 ? null : (
        <Section title="Synonyms" sectionKey={`explorer:${name}:${item}:synonyms`}>
          <p className="text-xs break-words">{flow.synonyms.join(', ')}</p>
        </Section>
      )}
    </section>
  )
}
