import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { useBackgroundProcess } from '@/api/queries'
import type { BackgroundExchange } from '@/api/types'
import { elementaryRefs, useElementaryFlows, type FlowSide } from '@/api/useFlowSides'
import { paths } from '@/lib/paths'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Section } from '@/window/Section'
import { useEditorTab } from '@/window/useEditorTab'
import { amountColumn, elementaryProvider, flowColumn, providerColumn, providerLink, unitColumn } from '../exchangeColumns'
import { splitBackgroundExchanges } from './exchanges'

function provider(exchange: BackgroundExchange, flows: Record<string, FlowSide>): ReactNode {
  if (exchange.cut_off !== null) return <span className="text-muted-foreground">cut off: {exchange.cut_off}</span>
  const input = exchange.input
  if (!input) return ''
  if (input.kind === 'background') return exchange.supplier ? providerLink(paths.background(input.database, input.id), 'product', exchange.supplier) : ''
  return elementaryProvider(flows[input.id])
}

export function BackgroundEditor() {
  const { name = '', ref = '' } = useParams()
  const read = useBackgroundProcess(name, ref)
  const process = read.data?.value
  const exchanges = process?.exchanges ?? []
  const { flows, errors } = useElementaryFlows(elementaryRefs(exchanges, (e) => e.flow))
  useEditorTab({ id: `background:${name}:${ref}`, kind: 'background', title: process?.name ?? ref, path: paths.background(name, ref) })
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!process) return <p className="p-4 text-muted-foreground">Loading…</p>
  const key = (s: string) => `background:${name}:${ref}:${s}`
  const split = splitBackgroundExchanges(exchanges)
  const columns: Column<BackgroundExchange>[] = [
    flowColumn((e) => e.flow, (e) => (e.type === 'elementary' ? 'elementary' : 'product')),
    amountColumn((e) => e.amount),
    unitColumn((e) => e.unit),
    providerColumn((e) => provider(e, flows)),
  ]
  const rowKey = (e: BackgroundExchange) => [e.flow, e.amount, e.unit, e.cut_off ?? '', e.input?.id ?? ''].join(':')
  const rowClass = (e: BackgroundExchange) => (e.reference ? 'font-semibold' : '')
  return (
    <>
      <EditorHeader icon="process" page="Background process" entity={process.name} />
      {errors.length > 0 ? <p className="px-4 text-destructive">{errors.join('; ')}</p> : null}
      <Section title="General information" sectionKey={key('general')}>
        <FieldGrid
          rows={[
            { label: 'Name', value: process.name },
            { label: 'Reference product', value: process.reference_product },
            { label: 'Location', value: process.location ?? '' },
            { label: 'Unit', value: process.unit },
            { label: 'Database', value: name },
            { label: 'Classifications', value: process.classifications.join('; ') },
            { label: 'Comment', value: process.comment ?? '' },
            ...(process.url ? [{ label: 'Source', value: <a href={process.url} target="_blank" rel="noreferrer">{process.url}</a> }] : []),
          ]}
        />
      </Section>
      <Section title="Inputs" sectionKey={key('inputs')}>
        <DataTable columns={columns} rows={split.inputs} rowKey={rowKey} rowClassName={rowClass} empty="No input." />
      </Section>
      <Section title="Outputs" sectionKey={key('outputs')}>
        <DataTable columns={columns} rows={split.outputs} rowKey={rowKey} rowClassName={rowClass} />
      </Section>
    </>
  )
}
