import { useFactors, useMethodTree } from '@/api/queries'
import type { Factor } from '@/api/types'
import { useAddress } from '@/lib/address'
import { formatAmount } from '@/lib/format'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { DataTable, NUMERIC, type Column } from '@/window/DataTable'
import { Section } from '@/window/Section'
import { DetailHeader } from './DetailHeader'
import { Facts } from './Facts'
import { ListingFilter, Pager } from './ListingControls'
import { findIndicator } from './methods'

const LIMIT = 25

export function IndicatorDetail({ name, item }: { name: string; item: string }) {
  const address = useAddress()
  const tree = useMethodTree(name)
  const query = address.read('fq')
  const cursor = address.read('fcursor') || undefined
  const read = useFactors(name, item, { query, limit: LIMIT, cursor })
  if (tree.error) return <p className="min-w-0 text-destructive">{tree.error.message}</p>
  if (tree.data === undefined) return <p className="min-w-0 text-muted-foreground">Loading…</p>
  const found = findIndicator(tree.data.value, item)
  const rows: [string, string][] =
    found === null
      ? []
      : [
          ['Family', found.family.name],
          ['Category', found.category.name],
          ['Unit', found.method.unit],
        ]
  const columns: Column<Factor>[] = [
    {
      key: 'flow',
      header: 'Flow',
      render: (factor) => (
        <AppLink to={paths.flow(name, factor.flow.id)} className="text-accent">
          {factor.name}
        </AppLink>
      ),
    },
    { key: 'compartment', header: 'Compartment', render: (factor) => factor.compartment },
    { key: 'sub', header: 'Sub-compartment', render: (factor) => factor.sub_compartment ?? '' },
    { key: 'unit', header: 'Unit', render: (factor) => factor.unit },
    { key: 'factor', header: 'Factor', align: 'right', render: (factor) => <span className={NUMERIC}>{formatAmount(factor.factor)}</span> },
  ]
  return (
    <section aria-label={found === null ? item : found.method.indicator} className="flex min-w-0 flex-col">
      <DetailHeader title={found === null ? item : found.method.indicator} />
      <Facts rows={rows} />
      <Section title="Factors" sectionKey={`explorer:${name}:${item}:factors`}>
        <ListingFilter
          id="explorer-factor-filter"
          label="Filter the factors"
          value={query}
          onChange={(value) => address.write({ fq: value, fcursor: undefined })}
        />
        {read.error ? (
          <p className="text-destructive">{read.error.message}</p>
        ) : read.data === undefined ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : (
          <>
            {read.data.value.total === null || query === '' ? null : (
              <p className="text-xs text-muted-foreground">{`${formatAmount(read.data.value.total)} ${read.data.value.total === 1 ? 'factor' : 'factors'}`}</p>
            )}
            <DataTable
              columns={columns}
              rows={read.data.value.items}
              rowKey={(factor) => factor.flow.id}
              empty={query === '' ? 'This indicator carries no factor.' : 'No match.'}
            />
            <Pager
              previous={read.data.value.previous_cursor}
              next={read.data.value.next_cursor}
              onPage={(cursor) => address.write({ fcursor: cursor })}
            />
          </>
        )}
      </Section>
    </section>
  )
}
