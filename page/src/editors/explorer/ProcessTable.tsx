import { useSearchProcesses, useUnderNode, useVocabulary } from '@/api/queries'
import type { ClassificationNode, ProcessHit } from '@/api/types'
import { useAddress } from '@/lib/address'
import { AppLink } from '@/lib/router'
import { DataTable, type Column } from '@/window/DataTable'
import { Hint } from '@/window/Hint'
import { Count, ListingFilter, ListingSelect, Pager, WholeDatabaseSwitch } from './ListingControls'

const LIMIT = 25

export function ProcessTable({
  name,
  scheme,
  node,
  everywhere = false,
}: {
  name: string
  scheme: string | null
  node: ClassificationNode | null
  everywhere?: boolean
}) {
  const address = useAddress()
  const query = address.read('q')
  const cursor = address.read('cursor') || undefined
  const item = address.read('item')
  const whole = everywhere || address.read('whole') === '1'
  const location = address.read('location')
  const unit = address.read('unit')
  const locations = useVocabulary(name, 'locations', whole)
  const units = useVocabulary(name, 'units', whole)
  const under = useUnderNode(name, whole ? null : scheme, {
    node: node?.id ?? '',
    query,
    limit: LIMIT,
    cursor,
    item: cursor === undefined ? item || undefined : undefined,
  })
  const searched = useSearchProcesses(name, {
    query: whole ? query : '',
    location: whole ? location || undefined : undefined,
    unit: whole ? unit || undefined : undefined,
    limit: LIMIT,
    cursor,
  })
  const items = (whole ? searched.data?.items : under.data?.value.items) ?? []
  const next = (whole ? searched.data?.next_cursor : under.data?.value.next_cursor) ?? null
  const previous = (whole ? null : under.data?.value.previous_cursor) ?? null
  const total = under.data?.value.total ?? null
  const error = whole ? searched.error : under.error
  const columns: Column<ProcessHit>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (hit) => (
        <AppLink to={address.href({ item: hit.ref.id })} className="text-accent">
          {hit.name}
        </AppLink>
      ),
    },
    { key: 'product', header: 'Reference product', render: (hit) => hit.reference_product },
    { key: 'location', header: 'Location', render: (hit) => hit.location ?? '' },
    { key: 'unit', header: 'Unit', render: (hit) => hit.unit },
  ]
  const empty = error?.message ?? (query !== '' ? 'No match.' : whole ? 'Search the database for a process.' : 'This node lists no process.')
  const search = (
    <WholeDatabaseSwitch
      id="explorer-whole-database"
      checked={whole}
      onChange={(on) => address.write({ whole: on ? '1' : '0', cursor: undefined })}
    />
  )
  return (
    <section aria-label="Processes" className="flex min-w-0 flex-col">
      {whole ? (
        <h2 className="min-w-0 break-words font-semibold">Whole-database search</h2>
      ) : node === null ? null : (
        <h2 className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="font-semibold">{node.label}</span>
          {node.name === null ? null : <span className="min-w-0 text-muted-foreground [overflow-wrap:anywhere]">{node.name}</span>}
          <Count kept={query === '' ? null : total} of={node.processes} />
        </h2>
      )}
      {node === null && !whole ? (
        <>
          {search}
          <p className="text-xs text-muted-foreground">Choose a node of the classification to list its processes.</p>
        </>
      ) : (
        <>
          <ListingFilter
            id="explorer-process-filter"
            label="Filter the processes"
            value={query}
            onChange={(value) => address.write({ q: value, cursor: undefined })}
          />
          {whole ? (
            <div className="flex min-w-0 flex-wrap items-center gap-2 py-1">
              <ListingSelect
                id="explorer-process-location"
                label="Location"
                value={location}
                options={(locations.data?.value ?? []).map((term) => ({
                  value: term.value,
                  label: term.detail === null ? term.value : `${term.value} · ${term.detail}`,
                }))}
                onChange={(value) => address.write({ location: value, cursor: undefined })}
              />
              <ListingSelect
                id="explorer-process-unit"
                label="Unit"
                value={unit}
                options={(units.data?.value ?? []).map((term) => ({ value: term.value, label: term.value }))}
                onChange={(value) => address.write({ unit: value, cursor: undefined })}
              />
            </div>
          ) : null}
          {everywhere ? null : search}
          <DataTable columns={columns} rows={items} rowKey={(hit) => hit.ref.id} current={address.read('item')} empty={empty} />
          {whole ? <Hint of={searched.data} /> : null}
          <Pager previous={previous} next={next} onPage={(cursor) => address.write({ cursor })} />
        </>
      )}
    </section>
  )
}
