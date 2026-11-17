import { useCompartments, useSearchElementaryFlows, useFlowsIn } from '@/api/queries'
import type { Compartment, ElementaryFlowHit, SubCompartment } from '@/api/types'
import { useAddress } from '@/lib/address'
import { formatAmount } from '@/lib/format'
import { AppLink } from '@/lib/router'
import { DataTable, type Column } from '@/window/DataTable'
import { Hint } from '@/window/Hint'
import { ListingFilter, ListingSelect, MorePages, WholeDatabaseSwitch } from './ListingControls'

const LIMIT = 25

export function FlowTable({ name, compartment, sub }: { name: string; compartment: Compartment | null; sub: SubCompartment | null }) {
  const address = useAddress()
  const query = address.read('q')
  const cursor = address.read('cursor') || undefined
  const whole = address.read('whole') === '1'
  const compartmentFilter = address.read('compartment_filter')
  const compartments = useCompartments(name, whole)
  const listed = useFlowsIn(name, whole ? null : (compartment?.name ?? null), {
    sub_compartment: whole ? undefined : sub?.name,
    query,
    limit: LIMIT,
    cursor,
  })
  const searched = useSearchElementaryFlows(name, {
    query: whole ? query : '',
    compartment: whole ? compartmentFilter || undefined : undefined,
    limit: LIMIT,
    cursor,
  })
  const items = (whole ? searched.data?.items : listed.data?.value.items) ?? []
  const more = (whole ? searched.data?.has_more : listed.data?.value.has_more) ?? false
  const next = (whole ? searched.data?.next_cursor : listed.data?.value.next_cursor) ?? null
  const error = whole ? searched.error : listed.error
  const columns: Column<ElementaryFlowHit>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (hit) => (
        <AppLink to={address.href({ item: hit.ref.id })} className="text-accent">
          {hit.name}
        </AppLink>
      ),
    },
    { key: 'compartment', header: 'Compartment', render: (hit) => hit.compartment },
    { key: 'sub', header: 'Sub-compartment', render: (hit) => hit.sub_compartment ?? '' },
    { key: 'unit', header: 'Unit', render: (hit) => hit.unit },
    { key: 'cas', header: 'CAS number', render: (hit) => hit.cas_number ?? '' },
  ]
  const empty = error?.message ?? (query !== '' ? 'No match.' : whole ? 'Search the database for a flow.' : 'This compartment lists no flow.')
  return (
    <section aria-label="Elementary flows" className="flex min-w-0 flex-col">
      {whole ? (
        <h2 className="min-w-0 break-words font-semibold">Whole-database search</h2>
      ) : compartment === null ? null : (
        <h2 className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="min-w-0 break-words font-semibold">{sub === null ? compartment.name : `${compartment.name} / ${sub.name}`}</span>
          <span className="text-xs tabular-nums text-muted-foreground">{formatAmount(sub === null ? compartment.flow_count : sub.flow_count)}</span>
        </h2>
      )}
      {compartment === null && !whole ? null : (
        <ListingFilter
          id="explorer-flow-filter"
          label="Filter the flows"
          value={query}
          onChange={(value) => address.write({ q: value, cursor: undefined })}
        />
      )}
      {whole ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2 py-1">
          <ListingSelect
            id="explorer-flow-compartment"
            label="Compartment"
            value={compartmentFilter}
            options={(compartments.data ?? []).map((term) => term.value)}
            onChange={(value) => address.write({ compartment_filter: value, cursor: undefined })}
          />
        </div>
      ) : null}
      {compartment === null ? null : (
        <WholeDatabaseSwitch
          id="explorer-flow-whole"
          checked={whole}
          onChange={(on) => address.write({ whole: on ? '1' : '0', cursor: undefined })}
        />
      )}
      {compartment === null && !whole ? (
        <p className="text-xs text-muted-foreground">Choose a compartment to list its flows.</p>
      ) : (
        <>
          <DataTable columns={columns} rows={items} rowKey={(hit) => hit.ref.id} empty={empty} />
          {whole ? <Hint of={searched.data} /> : null}
          <MorePages shown={more} onMore={() => address.write({ cursor: next ?? undefined })} />
        </>
      )}
    </section>
  )
}
