import { useQueries } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '@/api/client'
import { forever, keys } from '@/api/queries'
import type { Exchange, Process, ProductSystem } from '@/api/types'
import { useFlowSides, type FlowSide } from '@/api/useFlowSides'
import { paths } from '@/lib/paths'
import { describeUncertainty } from '@/lib/uncertainty'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import { amountColumn, elementaryProvider, flowColumn, providerColumn, providerLink, unitColumn } from '../exchangeColumns'
import { splitExchanges } from './exchanges'

interface ProviderInfo {
  name: string
  location: string | null
}

function provider(exchange: Exchange, systemId: string, system: ProductSystem, flows: Record<string, FlowSide>, providers: Record<string, ProviderInfo>): ReactNode {
  const input = exchange.input
  if (!input) return ''
  if (input.kind === 'foreground') {
    const target = system.processes.find((p) => p.code === input.code)
    return providerLink(paths.process(systemId, input.code), 'process', `${target?.name ?? input.code} · foreground`)
  }
  if (input.kind === 'system') {
    return providerLink(paths.system(input.product_system_id), 'system', `${exchange.name} · linked system`)
  }
  if (input.kind === 'background') {
    const found = providers[`${input.database}:${input.id}`]
    const label = found ? (found.location ? `${found.name} · ${found.location}` : found.name) : exchange.name
    return providerLink(paths.background(input.database, input.id), 'product', label)
  }
  return elementaryProvider(flows[input.id])
}

export function InputsOutputsPage({ systemId, system, process }: { systemId: string; system: ProductSystem; process: Process }) {
  const { sides, flows, errors: flowErrors } = useFlowSides(process.exchanges)
  const background = process.exchanges.filter((e) => e.input?.kind === 'background')
  const backgrounds = useQueries({
    queries: background.map((e) => {
      const ref = e.input as { database: string; id: string }
      return { queryKey: keys.background(ref.database, ref.id), queryFn: () => api.backgroundProcess(ref.database, ref.id), ...forever }
    }),
  })
  const providers: Record<string, ProviderInfo> = {}
  const providerErrors: string[] = []
  backgrounds.forEach((q, i) => {
    const ref = background[i].input as { database: string; id: string }
    if (q.data) providers[`${ref.database}:${ref.id}`] = { name: q.data.value.name, location: q.data.value.location }
    if (q.error) providerErrors.push(`${background[i].name}: ${q.error.message}`)
  })
  const errors = [...flowErrors, ...providerErrors]
  const split = splitExchanges(process, sides)
  const columns: Column<Exchange>[] = [
    flowColumn((e) => e.name, (e) => (e.type === 'elementary' ? 'elementary' : e.input?.kind === 'foreground' ? 'process' : 'product')),
    amountColumn((e) => e.amount),
    unitColumn((e) => e.unit),
    { key: 'formula', header: 'Formula', render: (e) => (e.formula ? <code>{e.formula}</code> : '') },
    { key: 'uncertainty', header: 'Uncertainty', render: (e) => describeUncertainty(e.uncertainty) },
    providerColumn((e) => provider(e, systemId, system, flows, providers)),
    { key: 'description', header: 'Description', render: (e) => e.comment ?? '' },
    { key: 'request', header: '', render: (e) => <RequestAction systemId={systemId} entity="exchange" entityId={e.id} /> },
  ]
  const key = (s: string) => `process:${systemId}:${process.code}:${s}`
  const action = <RequestAction systemId={systemId} entity="process" entityId={process.code} />
  const rowClass = (e: Exchange) => (e.type === 'production' ? 'font-semibold' : '')
  return (
    <>
      <EditorHeader icon="process" page="Inputs/Outputs" entity={process.name} />
      {errors.length > 0 ? <p className="px-4 text-destructive">{errors.join('; ')}</p> : null}
      <Section title="Inputs" sectionKey={key('inputs')} actions={action}>
        <DataTable columns={columns} rows={split.inputs} rowKey={(e) => e.id} rowClassName={rowClass} empty="No input." />
      </Section>
      <Section title="Outputs" sectionKey={key('outputs')} actions={action}>
        <DataTable columns={columns} rows={split.outputs} rowKey={(e) => e.id} rowClassName={rowClass} />
      </Section>
      {split.unresolved.length > 0 && flowErrors.length === 0 ? (
        <p className="px-4 text-xs text-muted-foreground">Resolving {split.unresolved.length} elementary flow{split.unresolved.length === 1 ? '' : 's'}…</p>
      ) : null}
    </>
  )
}
