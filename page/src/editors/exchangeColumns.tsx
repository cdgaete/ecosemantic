import type { ReactNode } from 'react'
import type { FlowSide } from '@/api/useFlowSides'
import { formatAmount } from '@/lib/format'
import { AppLink } from '@/lib/router'
import { NUMERIC, type Column } from '@/window/DataTable'
import { Icon, type IconName } from '@/window/Icon'

export function flowColumn<T>(name: (row: T) => string, icon: (row: T) => IconName, to?: (row: T) => string | null): Column<T> {
  return {
    key: 'flow',
    header: 'Flow',
    render: (row) => {
      const label = (
        <span className="flex min-w-0 items-center gap-1 break-words">
          <Icon name={icon(row)} />
          {name(row)}
        </span>
      )
      const href = to?.(row) ?? null
      return href === null ? label : (
        <AppLink to={href} className="text-accent">
          {label}
        </AppLink>
      )
    },
  }
}

export function amountColumn<T>(amount: (row: T) => number): Column<T> {
  return { key: 'amount', header: 'Amount', align: 'right', render: (row) => <span className={NUMERIC}>{formatAmount(amount(row))}</span> }
}

export function unitColumn<T>(unit: (row: T) => string): Column<T> {
  return { key: 'unit', header: 'Unit', render: (row) => unit(row) }
}

export function providerColumn<T>(provider: (row: T) => ReactNode): Column<T> {
  return { key: 'provider', header: 'Provider', render: provider }
}

export function providerLink(to: string, icon: IconName, label: string): ReactNode {
  return (
    <AppLink to={to} className="flex items-center gap-1 text-accent">
      <Icon name={icon} />
      {label}
    </AppLink>
  )
}

export function namedWithLocation(name: string, location: string | null): string {
  return location ? `${name} · ${location}` : name
}

export function elementaryProvider(flow: FlowSide | undefined): string {
  return flow ? `${flow.flow_type} · ${flow.compartment}` : ''
}
