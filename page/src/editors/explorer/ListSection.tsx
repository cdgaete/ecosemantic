import { useSummary, useVocabulary } from '@/api/queries'
import type { Term } from '@/api/types'
import { useAddress } from '@/lib/address'
import { formatAmount } from '@/lib/format'
import { DataTable, type Column } from '@/window/DataTable'
import { ListingFilter } from './ListingControls'
import { TITLES } from './sections'

function columns(kind: 'units' | 'locations'): Column<Term>[] {
  return [
    {
      key: 'value',
      header: kind === 'locations' ? 'Code' : 'Name',
      render: (term) => (
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="[overflow-wrap:anywhere]">{term.value}</span>
          {term.detail === null ? null : <span className="min-w-0 text-muted-foreground [overflow-wrap:anywhere]">{term.detail}</span>}
        </span>
      ),
    },
  ]
}

export function ListSection({ name, kind }: { name: string; kind: 'units' | 'locations' }) {
  const address = useAddress()
  const read = useVocabulary(name, kind)
  const summary = useSummary(name)
  const title = TITLES[kind]
  const count = summary.data?.value[kind]
  const filter = address.read('q')
  const term = filter.trim().toLocaleLowerCase()
  const terms = (read.data?.value ?? []).filter((entry) => `${entry.value} ${entry.detail ?? ''}`.toLocaleLowerCase().includes(term))
  return (
    <section aria-label={title} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto px-3 py-2">
      <h2 className="flex min-w-0 flex-wrap items-baseline gap-x-2">
        <span className="font-semibold">{title}</span>
        <span className="text-xs tabular-nums text-muted-foreground">{count === undefined ? '' : formatAmount(count)}</span>
      </h2>
      <ListingFilter
        id={`explorer-${kind}-filter`}
        label={`Filter the ${title.toLocaleLowerCase()}`}
        value={filter}
        onChange={(value) => address.write({ q: value })}
      />
      {read.error ? (
        <p className="text-destructive">{read.error.message}</p>
      ) : read.data === undefined ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : (
        <DataTable columns={columns(kind)} rows={terms} rowKey={(entry) => entry.value} empty={filter === '' ? `This database lists no ${title.toLocaleLowerCase()}.` : 'No match.'} />
      )}
    </section>
  )
}
