import { Handle, Position, useStore, type NodeProps } from '@xyflow/react'
import { memo, type CSSProperties, type ReactNode } from 'react'
import type { Exchange } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { Icon, type IconName } from '@/window/Icon'
import type { ProcessNodeType } from './build'
import { detailAt } from './layout'

function iconOf(exchange: Exchange): IconName {
  if (exchange.type === 'elementary') return 'elementary'
  if (exchange.input?.kind === 'foreground') return 'process'
  return 'product'
}

function foldLabel(hidden: Exchange[]): string {
  const idle = hidden.filter((e) => e.amount === 0).length
  return `Show ${hidden.length} more inputs${idle > 0 ? `, ${idle} of them at zero` : ''}`
}

function amountCell(exchange: Exchange, scaled: Record<string, number> | null, values: boolean): ReactNode {
  if (scaled !== null) {
    const value = scaled[exchange.id]
    if (value === undefined) return <span title="No scaled amount for this row">?</span>
    if (exchange.formula && !values) return <span title={exchange.formula}>ƒ {formatAmount(value)}</span>
    return <span title={exchange.formula ?? undefined}>{formatAmount(value)}</span>
  }
  if (exchange.formula && !values) return <span title={exchange.formula}>ƒ</span>
  return <span title={exchange.formula ?? undefined}>{formatAmount(exchange.amount)}</span>
}

function Row({ exchange, systemId, hot, scaled }: { exchange: Exchange; systemId: string; hot: boolean; scaled: Record<string, number> | null }) {
  const values = useUi((s) => s.formulaValues)
  const amount = amountCell(exchange, scaled, values)
  const name =
    exchange.input?.kind === 'background' ? (
      <AppLink to={paths.background(exchange.input.database, exchange.input.id)} title={exchange.name} className="truncate hover:underline nodrag nopan">
        {exchange.name}
      </AppLink>
    ) : exchange.input?.kind === 'foreground' ? (
      <AppLink to={paths.process(systemId, exchange.input.code)} title={exchange.name} className="truncate hover:underline nodrag nopan">
        {exchange.name}
      </AppLink>
    ) : (
      <span title={exchange.name} className="truncate">
        {exchange.name}
      </span>
    )
  return (
    <div
      data-zero={exchange.amount === 0}
      className={cn(
        'grid h-[22px] grid-cols-[16px_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-md px-1',
        exchange.type === 'production' && 'font-semibold',
        exchange.amount === 0 && 'text-muted-foreground opacity-60',
        hot && 'flash shadow-[0_0_0_2px_rgb(var(--highlight))]',
      )}
    >
      <Icon name={iconOf(exchange)} />
      {name}
      <span className="text-right tabular-nums">{amount}</span>
      <span className="text-muted-foreground">{exchange.unit}</span>
    </div>
  )
}

function ProcessNodeComponent({ data }: NodeProps<ProcessNodeType>) {
  const { process, reference, hot, hotExchanges, outline, systemId, placement } = data
  const byId = new Map(process.exchanges.map((e) => [e.id, e]))
  const inputs = placement.inputs.flatMap((port) => byId.get(port.exchange_id) ?? [])
  const outputs = placement.outputs.flatMap((exchangeId) => byId.get(exchangeId) ?? [])
  const detail = useStore((s) => detailAt(s.transform[2]))
  const chosen = useUi((s) => s.chosenProcess === process.id)
  const listed = inputs.slice(0, placement.shown_inputs)
  const hidden = inputs.slice(placement.shown_inputs)
  return (
    <div
      style={{ height: placement.height, ...(outline ? ({ '--outline': outline } as CSSProperties) : {}) }}
      data-chosen={chosen || undefined}
      className={cn(
        'w-[300px] overflow-hidden rounded-xl bg-background text-xs shadow-sm outline outline-[1.5px] -outline-offset-[1.5px] outline-node-border',
        reference && 'outline-[2.5px] -outline-offset-[2.5px]',
        hot && !outline && !chosen && 'shadow-[0_0_0_3px_rgb(var(--highlight))]',
        chosen && !outline && 'shadow-[0_0_0_3px_rgb(var(--accent))]',
        outline && 'shadow-[0_0_0_3px_var(--outline)]',
      )}
    >
      {placement.inputs.map((port) => (
        <Handle key={port.exchange_id} type="target" position={Position.Left} id={port.exchange_id} style={{ top: port.y }} className="!bg-link-stroke" />
      ))}
      <Handle type="source" position={Position.Right} id="out" style={{ top: placement.output }} className="!bg-link-stroke" />
      <div className={cn('flex gap-2 overflow-hidden px-3 font-semibold leading-snug', detail === 'rows' ? 'h-[40px] items-start py-1' : 'h-full items-start py-3 text-2xl')}>
        <Icon name="process" />
        <AppLink to={paths.process(systemId, process.code)} title={process.name} className={cn('min-w-0 hover:underline nodrag nopan', detail === 'rows' ? 'line-clamp-1 break-all' : 'line-clamp-3 [overflow-wrap:anywhere]')}>
          {process.name}
        </AppLink>
        <span className="ml-auto shrink-0 rounded-full bg-muted px-1.5 font-normal text-muted-foreground">{process.location}</span>
      </div>
      {detail === 'rows' ? (
        <>
          <div className="px-2 py-[6px]">
            <div className="h-[18px] px-1 text-xs text-muted-foreground">›› Input flows</div>
            {listed.map((e) => (
              <Row key={e.id} exchange={e} systemId={systemId} hot={hotExchanges.includes(e.id)} scaled={placement.scaled} />
            ))}
            {hidden.length > 0 ? (
              <AppLink to={paths.process(systemId, process.code, 'io')} className="nodrag nopan block h-[22px] w-full rounded-md text-center leading-[22px] text-muted-foreground hover:bg-foreground/8 hover:text-foreground">
                {foldLabel(hidden)}
              </AppLink>
            ) : null}
          </div>
          <div className="px-2 py-[6px] shadow-[inset_0_1px_0_rgb(var(--node-border))]">
            <div className="h-[18px] px-1 text-right text-xs text-muted-foreground">Output flows ››</div>
            {outputs.map((e) => (
              <Row key={e.id} exchange={e} systemId={systemId} hot={hotExchanges.includes(e.id)} scaled={placement.scaled} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}

export const ProcessNode = memo(ProcessNodeComponent)
