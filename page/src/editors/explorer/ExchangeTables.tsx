import type { ReactNode } from 'react'
import type { BackgroundExchange } from '@/api/types'
import { elementaryRefs, useElementaryFlows, type FlowSide } from '@/api/useFlowSides'
import { splitBackgroundExchanges } from '@/editors/explorer/exchanges'
import { amountColumn, elementaryProvider, flowColumn, namedWithLocation, providerColumn, providerLink, unitColumn } from '@/editors/exchangeColumns'
import { DataTable, type Column } from '@/window/DataTable'
import { Section } from '@/window/Section'
import type { DatasetLinks } from './links'

function provider(exchange: BackgroundExchange, flows: Record<string, FlowSide>, links: DatasetLinks): ReactNode {
  if (exchange.cut_off !== null) return <span className="text-muted-foreground">cut off: {exchange.cut_off}</span>
  const input = exchange.input
  if (!input) return ''
  if (input.kind === 'background') return exchange.supplier ? providerLink(links.process(input.database, input.id), 'product', namedWithLocation(exchange.supplier, exchange.supplier_location)) : ''
  return elementaryProvider(flows[input.id])
}

function rowKey(exchange: BackgroundExchange): string {
  return [exchange.flow, exchange.amount, exchange.unit, exchange.cut_off ?? '', exchange.input?.id ?? ''].join(':')
}

function rowClass(exchange: BackgroundExchange): string {
  return exchange.reference ? 'font-semibold' : ''
}

export function BackgroundExchangeTables({ database, exchanges, sectionKey, links }: { database: string; exchanges: BackgroundExchange[]; sectionKey: string; links: DatasetLinks }) {
  const { flows, errors } = useElementaryFlows(elementaryRefs(exchanges, (exchange) => exchange.flow))
  const split = splitBackgroundExchanges(exchanges)
  const columns: Column<BackgroundExchange>[] = [
    flowColumn(
      (exchange) => exchange.flow,
      (exchange) => (exchange.type === 'elementary' ? 'elementary' : 'product'),
      (exchange) => (exchange.input?.kind === 'elementary_flow' ? links.flow(database, exchange.input.id) : null),
    ),
    amountColumn((exchange) => exchange.amount),
    unitColumn((exchange) => exchange.unit),
    providerColumn((exchange) => provider(exchange, flows, links)),
  ]
  return (
    <>
      {errors.length > 0 ? <p className="px-4 text-destructive">{errors.join('; ')}</p> : null}
      <Section title="Inputs" sectionKey={`${sectionKey}:inputs`}>
        <DataTable columns={columns} rows={split.inputs} rowKey={rowKey} rowClassName={rowClass} empty="No input." />
      </Section>
      <Section title="Outputs" sectionKey={`${sectionKey}:outputs`}>
        <DataTable columns={columns} rows={split.outputs} rowKey={rowKey} rowClassName={rowClass} />
      </Section>
    </>
  )
}
