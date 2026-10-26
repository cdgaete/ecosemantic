import type { ReactNode } from 'react'
import type { FlowSide } from '@/api/useFlowSides'
import { formatAmount } from '@/lib/format'
import { AppLink } from '@/lib/router'
import type { Column } from '@/window/DataTable'
import { Icon, type IconName } from '@/window/Icon'

export function flowColumn<T>(name: (row: T) => string, icon: (row: T) => IconName): Column<T> {
  return {
    key: 'flow',
    header: 'Flow',
    render: (row) => (
      <span className="flex items-center gap-1">
        <Icon name={icon(row)} />
        {name(row)}
      </span>
    ),
  }
}

export function amountColumn<T>(amount: (row: T) => number): Column<T> {
  return { key: 'amount', header: 'Amount', align: 'right', render: (row) => formatAmount(amount(row)) }
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

export function elementaryProvider(flow: FlowSide | undefined): string {
  return flow ? `${flow.flow_type} · ${flow.compartment}` : ''
}
