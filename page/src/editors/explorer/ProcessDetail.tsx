import { useState, type ReactNode } from 'react'
import { useBackgroundProcess } from '@/api/queries'
import type { BackgroundProcess } from '@/api/types'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { DataTable, type Column } from '@/window/DataTable'
import { Section } from '@/window/Section'
import { DetailHeader } from './DetailHeader'
import { BackgroundExchangeTables } from './ExchangeTables'
import { Facts } from './Facts'
import { EXPLORER_LINKS, type DatasetLinks } from './links'

interface Classification {
  scheme: string
  values: string[]
}

function rest(stored: string, scheme: string): string {
  const head = `${scheme}: `
  return stored.startsWith(head) ? stored.slice(head.length) : stored
}

function byScheme(classifications: string[]): Classification[] {
  const rows: Classification[] = []
  for (const stored of classifications) {
    const at = stored.indexOf(': ')
    const scheme = at < 0 ? stored : stored.slice(0, at)
    const known = rows.find((row) => row.scheme === scheme)
    if (known === undefined) rows.push({ scheme, values: [stored] })
    else known.values.push(stored)
  }
  return rows
}

function firstSentence(text: string): string {
  const end = text.indexOf('. ')
  return end < 0 ? text : text.slice(0, end + 1)
}

function factsOf(name: string, process: BackgroundProcess): [string, string][] {
  return [
    ['Reference product', process.reference_product],
    ['Location', process.location ?? ''],
    ['Unit', process.unit],
    ['Database', name],
  ]
}

function listed(title: string): ReactNode {
  return <DetailHeader title={title} />
}

/** One background process: its facts, classifications, comment and exchanges, under the header and with the links its place gives it; the explorer's by default. */
export function ProcessDetail({
  name,
  item,
  links = EXPLORER_LINKS,
  header = listed,
}: {
  name: string
  item: string
  links?: DatasetLinks
  header?: (title: string) => ReactNode
}) {
  const read = useBackgroundProcess(name, item)
  const [opened, setOpened] = useState(false)
  const process = read.data?.value
  if (read.error) return <p className="min-w-0 text-destructive">{read.error.message}</p>
  if (process === undefined) return <p className="min-w-0 text-muted-foreground">Loading…</p>
  const classifications = byScheme(process.classifications)
  const comment = process.comment
  const folded = comment === null ? null : firstSentence(comment)
  const columns: Column<Classification>[] = [
    { key: 'scheme', header: 'Scheme', render: (row) => <span className="[overflow-wrap:anywhere]">{row.scheme}</span> },
    {
      key: 'value',
      header: 'Value',
      render: (row) => (
        <span className="flex min-w-0 flex-col gap-0.5">
          {row.values.map((stored) => (
            <AppLink
              key={stored}
              to={paths.explorer(name, 'datasets', `?${new URLSearchParams({ scheme: row.scheme, value: stored }).toString()}`)}
              className="min-w-0 text-accent [overflow-wrap:anywhere]"
            >
              {rest(stored, row.scheme)}
            </AppLink>
          ))}
        </span>
      ),
    },
  ]
  const key = `explorer:${name}:${item}`
  return (
    <section aria-label={process.name} className="flex min-w-0 flex-col">
      {header(process.name)}
      <Facts rows={factsOf(name, process)} />
      {process.url === null ? null : (
        <a href={process.url} target="_blank" rel="noreferrer" className="min-w-0 pt-1 text-xs text-accent [overflow-wrap:anywhere]">
          {process.url}
        </a>
      )}
      <Section title="Classifications" sectionKey={`${key}:classifications`}>
        <DataTable columns={columns} rows={classifications} rowKey={(row) => row.scheme} empty="This process carries no classification." />
      </Section>
      {comment === null ? null : (
        <Section title="Comment" sectionKey={`${key}:comment`}>
          <p className="text-xs break-words">
            {opened ? comment : folded}
            {folded === comment ? null : (
              <button type="button" className="ml-1 text-accent" onClick={() => setOpened(!opened)}>
                {opened ? 'Less' : 'More'}
              </button>
            )}
          </p>
        </Section>
      )}
      <BackgroundExchangeTables database={name} exchanges={process.exchanges ?? []} sectionKey={key} links={links} />
    </section>
  )
}
