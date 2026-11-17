import { useSearchMethods } from '@/api/queries'
import type { Method, MethodCategory } from '@/api/types'
import { useAddress } from '@/lib/address'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { DataTable, type Column } from '@/window/DataTable'
import { Hint } from '@/window/Hint'
import { ListingFilter, MorePages, WholeDatabaseSwitch } from './ListingControls'

const LIMIT = 25

export function IndicatorTable({ name, category }: { name: string; category: MethodCategory | null }) {
  const address = useAddress()
  const query = address.read('q')
  const cursor = address.read('cursor') || undefined
  const whole = address.read('whole') === '1'
  const searched = useSearchMethods(name, { query: whole ? query : '', limit: LIMIT, cursor })
  const term = query.trim().toLocaleLowerCase()
  const items = whole ? (searched.data?.items ?? []) : (category?.indicators ?? []).filter((method) => method.indicator.toLocaleLowerCase().includes(term))
  const columns: Column<Method>[] = [
    {
      key: 'name',
      header: 'Indicator',
      render: (method) => (
        <AppLink to={paths.indicator(name, method.id)} className="text-accent">
          {method.indicator}
        </AppLink>
      ),
    },
    { key: 'unit', header: 'Unit', render: (method) => method.unit },
    ...(whole
      ? [
          { key: 'method', header: 'Method', render: (method: Method) => method.impact_method },
          { key: 'category', header: 'Category', render: (method: Method) => method.impact_category },
        ]
      : []),
  ]
  const empty =
    searched.error?.message ?? (query !== '' ? 'No match.' : whole ? 'Search the database for an impact method.' : 'This category lists no indicator.')
  return (
    <section aria-label="Indicators" className="flex min-w-0 flex-col">
      {category === null ? null : <h2 className="min-w-0 break-words font-semibold">{category.name}</h2>}
      {category === null && !whole ? null : (
        <ListingFilter
          id="explorer-indicator-filter"
          label="Filter the indicators"
          value={query}
          onChange={(value) => address.write({ q: value, cursor: undefined })}
        />
      )}
      {category === null ? null : (
        <WholeDatabaseSwitch id="explorer-indicator-whole" checked={whole} onChange={(on) => address.write({ whole: on ? '1' : '0', cursor: undefined })} />
      )}
      {category === null && !whole ? (
        <p className="text-xs text-muted-foreground">Choose a category of the impact methods to list its indicators.</p>
      ) : (
        <>
          <DataTable columns={columns} rows={items} rowKey={(method) => method.id} empty={empty} />
          {whole ? <Hint of={searched.data} /> : null}
          <MorePages
            shown={whole && (searched.data?.has_more ?? false)}
            onMore={() => address.write({ cursor: searched.data?.next_cursor ?? undefined })}
          />
        </>
      )}
    </section>
  )
}
