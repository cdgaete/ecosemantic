import { useQueries } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api } from '@/api/client'
import { forever, keys, useCompartments, useInventory } from '@/api/queries'
import type { InventoryArguments, InventoryOrder, InventoryRow, LinkedProcessRef, ProductSystem, Side } from '@/api/types'
import { namedWithLocation } from '@/editors/exchangeColumns'
import { formatAmount } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

const BASE_COLUMNS: Column<InventoryRow>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (r) => (
      <span className="flex items-center gap-1">
        <Icon name="elementary" />
        {r.name}
      </span>
    ),
  },
  { key: 'compartment', header: 'Compartment', folds: true, render: (r) => r.compartment },
  { key: 'sub', header: 'Sub-compartment', folds: true, render: (r) => r.sub_compartment ?? '' },
  { key: 'amount', header: 'Amount', align: 'right', render: (r) => formatAmount(r.amount) },
  { key: 'unit', header: 'Unit', render: (r) => r.unit },
]

interface AtVersion {
  name: string | null
  location: string | null
  error: string | null
}

function linkKey(link: LinkedProcessRef): string {
  return `${link.product_system_id}:${link.at_hash}:${link.code}`
}

function distinctLinks(rows: InventoryRow[]): LinkedProcessRef[] {
  const links = new Map<string, LinkedProcessRef>()
  for (const row of rows) if (row.source?.kind === 'linked') links.set(linkKey(row.source), row.source)
  return [...links.values()]
}

function namedSource(row: InventoryRow, system: ProductSystem | undefined, at: Map<string, AtVersion>): ReactNode {
  const source = row.source
  if (source === null) return ''
  if (source.kind === 'foreground') {
    const process = system?.processes.find((p) => p.code === source.code)
    return <span title={source.code}>{process === undefined ? source.code : namedWithLocation(process.name, process.location)}</span>
  }
  const read = at.get(linkKey(source))
  if (read === undefined) return <span title={source.code}>{source.code}</span>
  if (read.error !== null) return <span title={source.code}>{read.error}</span>
  if (read.name === null) return <span title={source.code}>{source.code}</span>
  return <span title={source.code}>{namedWithLocation(read.name, read.location)}</span>
}

const ORDER_OPTIONS: { value: InventoryOrder; label: string }[] = [
  { value: 'compartment', label: 'compartment, then name' },
  { value: 'amount', label: 'largest amount first' },
]

function SideTable({
  id,
  hash,
  side,
  title,
  body,
  enabled,
  waiting,
  sectionKey,
  actions,
  system,
}: {
  id: string
  hash: string
  side: Side
  title: string
  body: Omit<InventoryArguments, 'side' | 'cursor'>
  enabled: boolean
  waiting: string
  sectionKey: string
  actions: ReactNode
  system: ProductSystem | undefined
}) {
  const [cursor, setCursor] = useState<string | undefined>()
  const [earlier, setEarlier] = useState<(string | undefined)[]>([])
  const rows = useInventory(id, hash, { ...body, side, cursor }, enabled)
  const items = rows.data?.items ?? []
  const links = distinctLinks(items)
  const versions = useQueries({
    queries: links.map((link) => ({ queryKey: keys.version(link.product_system_id, link.at_hash), queryFn: () => api.version(link.product_system_id, link.at_hash), ...forever })),
  })
  const at = new Map<string, AtVersion>()
  links.forEach((link, i) => {
    const answer = versions[i]
    if (answer.isPending) return
    const process = answer.data?.processes.find((held) => held.code === link.code)
    at.set(linkKey(link), { name: process?.name ?? null, location: process?.location ?? null, error: answer.error?.message ?? null })
  })
  const columns: Column<InventoryRow>[] = [
    ...BASE_COLUMNS,
    { key: 'source', header: 'Dominant process', folds: true, render: (r) => namedSource(r, system, at) },
  ]
  return (
    <Section title={title} sectionKey={sectionKey} actions={actions}>
      <DataTable columns={columns} rows={items} rowKey={(r) => r.flow.id} empty={rows.data ? `No ${title.toLowerCase()} on this page.` : waiting} />
      {rows.error ? <p className="text-xs text-destructive">{rows.error.message}</p> : null}
      <Hint of={rows.data} />
      <div className="flex gap-3 text-xs">
        {earlier.length > 0 ? (
          <button
            type="button"
            className="text-accent"
            onClick={() => {
              setCursor(earlier.at(-1))
              setEarlier(earlier.slice(0, -1))
            }}
          >
            Previous page
          </button>
        ) : null}
        {rows.data?.has_more ? (
          <button
            type="button"
            className="text-accent"
            onClick={() => {
              setEarlier([...earlier, cursor])
              setCursor(rows.data?.next_cursor ?? undefined)
            }}
          >
            Next page
          </button>
        ) : null}
      </div>
    </Section>
  )
}

export function InventoryPage({ result }: { result: Result }) {
  const { id, params, system, hash, root, stale, waiting, state, variant } = result
  const [compartment, setCompartment] = useState('')
  const [typed, setTyped] = useState('')
  const [query, setQuery] = useState('')
  const [order, setOrder] = useState<InventoryOrder>('compartment')
  const compartments = useCompartments(system?.database.name ?? '')
  const key = (s: string) => `results:${id}:inventory:${s}`
  const action = <RequestAction systemId={id} entity="product_system" entityId={id} />
  const body = {
    compartment: compartment || undefined,
    query: query || undefined,
    order,
    limit: 100,
    demand: demandOf(params!, root),
    ...(variant !== null ? { variant } : {}),
  }
  const table = { id, hash, body, enabled: !stale, waiting, actions: action, system }
  const resetKey = `${compartment}|${query}|${order}`
  return (
    <>
      <EditorHeader icon="result" page="Inventory results" entity={system?.name ?? ''} state={state} />
      <div className="flex flex-wrap items-center gap-3 px-4 pb-2 text-xs">
        <label className="flex min-w-0 max-w-full items-center gap-1">
          Compartment
          <select
            id="inventory-compartment"
            className="min-w-0 max-w-full rounded-sm border bg-background px-1"
            value={compartment}
            onChange={(e) => setCompartment(e.target.value)}
          >
            <option value="">any</option>
            {(compartments.data ?? []).map((t) => (
              <option key={t.value} value={t.value}>
                {t.value}
                {t.detail ? ` (${t.detail})` : ''}
              </option>
            ))}
          </select>
        </label>
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault()
            setQuery(typed)
          }}
        >
          <label htmlFor="inventory-query" className="flex items-center gap-1">
            Name
            <input id="inventory-query" className="rounded-sm border bg-background px-1" placeholder="flow name…" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </label>
          <button type="submit" className="rounded-sm border px-2">
            Search
          </button>
        </form>
        <label className="flex min-w-0 max-w-full items-center gap-1">
          Order
          <select
            id="inventory-order"
            className="min-w-0 max-w-full rounded-sm border bg-background px-1"
            value={order}
            onChange={(e) => setOrder(e.target.value as InventoryOrder)}
          >
            {ORDER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <SideTable key={`inputs|${resetKey}`} {...table} side="input" title="Inputs" sectionKey={key('inputs')} />
      <SideTable key={`outputs|${resetKey}`} {...table} side="output" title="Outputs" sectionKey={key('outputs')} />
    </>
  )
}
