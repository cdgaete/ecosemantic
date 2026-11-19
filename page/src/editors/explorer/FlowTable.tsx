import { useCompartments, useSearchElementaryFlows, useFlowsIn } from '@/api/queries'
import type { Compartment, ElementaryFlowHit, SubCompartment } from '@/api/types'
import { useAddress } from '@/lib/address'
import { AppLink } from '@/lib/router'
import { DataTable, MACHINE, type Column } from '@/window/DataTable'
import { Hint } from '@/window/Hint'
import { Count, ListingFilter, ListingSelect, Pager, WholeDatabaseSwitch } from './ListingControls'

const LIMIT = 25

export function FlowTable({ name, compartment, sub }: { name: string; compartment: Compartment | null; sub: SubCompartment | null }) {
  const address = useAddress()
  const query = address.read('q')
  const cursor = address.read('cursor') || undefined
  const item = address.read('item')
  const whole = address.read('whole') === '1'
  const compartmentFilter = address.read('compartment_filter')
  const compartments = useCompartments(name, whole)
  const listed = useFlowsIn(name, whole ? null : (compartment?.name ?? null), {
    sub_compartment: whole ? undefined : sub?.name,
    query,
    limit: LIMIT,
    cursor,
    item: cursor === undefined ? item || undefined : undefined,
  })
  const searched = useSearchElementaryFlows(name, {
    query: whole ? query : '',
    compartment: whole ? compartmentFilter || undefined : undefined,
    limit: LIMIT,
    cursor,
  })
  const items = (whole ? searched.data?.items : listed.data?.value.items) ?? []
  const next = (whole ? searched.data?.next_cursor : listed.data?.value.next_cursor) ?? null
  const previous = (whole ? null : listed.data?.value.previous_cursor) ?? null
  const total = listed.data?.value.total ?? null
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
    {
      key: 'cas',
      header: 'CAS number',
      render: (hit) =>
        hit.cas_number !== null ? (
          <span className={MACHINE}>{hit.cas_number}</span>
        ) : hit.cas_as_published === null ? (
          ''
        ) : (
          <>
            <span className={MACHINE}>{hit.cas_as_published}</span> (as published)
          </>
        ),
    },
  ]
  const empty = error?.message ?? (query !== '' ? 'No match.' : whole ? 'Search the database for a flow.' : 'This compartment lists no flow.')
  const search = (
    <WholeDatabaseSwitch
      id="explorer-flow-whole"
      checked={whole}
      onChange={(on) => address.write({ whole: on ? '1' : '0', cursor: undefined })}
    />
  )
  return (
    <section aria-label="Elementary flows" className="flex min-w-0 flex-col">
      {whole ? (
        <h2 className="min-w-0 break-words font-semibold">Whole-database search</h2>
      ) : compartment === null ? null : (
        <h2 className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="min-w-0 break-words font-semibold">{sub === null ? compartment.name : `${compartment.name} / ${sub.name}`}</span>
          <Count kept={query === '' ? null : total} of={sub === null ? compartment.flow_count : sub.flow_count} />
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
      {compartment === null && !whole ? (
        <>
          {search}
          <p className="text-xs text-muted-foreground">Choose a compartment to list its flows.</p>
        </>
      ) : (
        <>
          {whole ? (
            <div className="flex min-w-0 flex-wrap items-center gap-2 py-1">
              <ListingSelect
                id="explorer-flow-compartment"
                label="Compartment"
                value={compartmentFilter}
                options={(compartments.data ?? []).map((term) => ({ value: term.value, label: term.value }))}
                onChange={(value) => address.write({ compartment_filter: value, cursor: undefined })}
              />
            </div>
          ) : null}
          {search}
          <DataTable columns={columns} rows={items} rowKey={(hit) => hit.ref.id} current={address.read('item')} empty={empty} />
          {whole ? <Hint of={searched.data} /> : null}
          <Pager previous={previous} next={next} onPage={(cursor) => address.write({ cursor })} />
        </>
      )}
    </section>
  )
}
