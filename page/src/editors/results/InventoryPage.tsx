import { useState } from 'react'
import { useInventory, useVocabulary } from '@/api/queries'
import type { InventoryRow } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Icon } from '@/window/Icon'
import { Section } from '@/window/Section'
import { demandOf } from './params'
import type { Result } from './ResultsEditor'

const columns: Column<InventoryRow>[] = [
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
  { key: 'compartment', header: 'Compartment', render: (r) => r.compartment },
  { key: 'sub', header: 'Sub-compartment', render: (r) => r.sub_compartment ?? '' },
  { key: 'amount', header: 'Amount', align: 'right', render: (r) => formatAmount(r.amount) },
  { key: 'unit', header: 'Unit', render: (r) => r.unit },
  { key: 'source', header: 'Dominant process', render: (r) => r.source?.code ?? '' },
]

export function InventoryPage({ result }: { result: Result }) {
  const { id, params, system, hash, root, stale, waiting } = result
  const [compartment, setCompartment] = useState('')
  const [typed, setTyped] = useState('')
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState<string | undefined>()
  const [earlier, setEarlier] = useState<(string | undefined)[]>([])
  const restart = () => {
    setCursor(undefined)
    setEarlier([])
  }
  const compartments = useVocabulary(system?.database.name ?? '', 'compartments')
  const rows = useInventory(id, hash, { compartment: compartment || undefined, query: query || undefined, limit: 100, cursor, demand: demandOf(params!, root) }, !stale)
  const items = rows.data?.items ?? []
  const key = (s: string) => `results:${id}:inventory:${s}`
  const action = <RequestAction systemId={id} entity="product_system" entityId={id} />
  return (
    <>
      <EditorHeader icon="result" page="Inventory results" entity={system?.name ?? ''} />
      <div className="flex flex-wrap items-center gap-3 px-4 pb-2 text-xs">
        <label className="flex min-w-0 max-w-full items-center gap-1">
          Compartment
          <select
            id="inventory-compartment"
            className="min-w-0 max-w-full rounded-sm border bg-background px-1"
            value={compartment}
            onChange={(e) => {
              setCompartment(e.target.value)
              restart()
            }}
          >
            <option value="">any</option>
            {(compartments.data?.value ?? [])
              .filter((t) => !t.value.includes('/'))
              .map((t) => (
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
            restart()
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
        {rows.error ? <span className="text-destructive">{rows.error.message}</span> : null}
      </div>
      <Section title="Inputs" sectionKey={key('inputs')} actions={action}>
        <DataTable columns={columns} rows={items.filter((r) => r.side === 'input')} rowKey={(r) => r.flow.id} empty={rows.data ? 'No input on this page.' : waiting} />
      </Section>
      <Section title="Outputs" sectionKey={key('outputs')} actions={action}>
        <DataTable columns={columns} rows={items.filter((r) => r.side === 'output')} rowKey={(r) => r.flow.id} empty={rows.data ? 'No output on this page.' : waiting} />
      </Section>
      <div className="px-4">
        <Hint of={rows.data} />
      </div>
      {earlier.length > 0 ? (
        <button
          type="button"
          className="px-4 text-xs text-accent"
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
          className="px-4 text-xs text-accent"
          onClick={() => {
            setEarlier([...earlier, cursor])
            setCursor(rows.data?.next_cursor ?? undefined)
          }}
        >
          Next page
        </button>
      ) : null}
    </>
  )
}
