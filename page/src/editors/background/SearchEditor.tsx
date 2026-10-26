import { useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { useSearchElementaryFlows, useSearchMethods, useSearchProcesses, useVocabulary } from '@/api/queries'
import type { ElementaryFlowHit, Method, ProcessHit } from '@/api/types'
import { useAddress, type Address } from '@/lib/address'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { DataTable } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Hint } from '@/window/Hint'
import { Section } from '@/window/Section'
import { useEditorTab } from '@/window/useEditorTab'

const TITLES = { processes: 'Processes', 'elementary-flows': 'Elementary flows', methods: 'Impact methods' } as const

type SearchKind = keyof typeof TITLES

function isSearchKind(kind: string): kind is SearchKind {
  return Object.hasOwn(TITLES, kind)
}

function Select({ id, label, value, options, onChange }: { id: string; label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <label className="flex min-w-0 max-w-full items-center gap-1 text-xs">
      {label}
      <select id={id} className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">any</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}

function Processes({ database, address }: { database: string; address: Address }) {
  const query = address.read('q')
  const location = address.read('location')
  const unit = address.read('unit')
  const cursor = address.read('cursor') || undefined
  const locations = useVocabulary(database, 'locations')
  const units = useVocabulary(database, 'units')
  const hits = useSearchProcesses(database, { query, location: location || undefined, unit: unit || undefined, limit: 25, cursor })
  return (
    <>
      <div className="flex flex-wrap gap-3 pb-2">
        <Select id="search-location" label="Location" value={location} options={(locations.data?.value ?? []).map((t) => t.value)} onChange={(v) => address.write({ location: v, cursor: undefined })} />
        <Select id="search-unit" label="Unit" value={unit} options={(units.data?.value ?? []).map((t) => t.value)} onChange={(v) => address.write({ unit: v, cursor: undefined })} />
      </div>
      <DataTable<ProcessHit>
        columns={[
          {
            key: 'name',
            header: 'Name',
            render: (h) => (
              <AppLink to={paths.background(database, h.ref.id)} className="text-accent">
                {h.name}
              </AppLink>
            ),
          },
          { key: 'product', header: 'Reference product', render: (h) => h.reference_product },
          { key: 'location', header: 'Location', render: (h) => h.location ?? '' },
          { key: 'unit', header: 'Unit', render: (h) => h.unit },
        ]}
        rows={hits.data?.items ?? []}
        rowKey={(h) => h.ref.id}
        empty={hits.error?.message ?? (query ? 'No match.' : 'Type a query.')}
      />
      {hits.data && hits.data.items.length === 0 ? <p className="pt-1 text-xs text-muted-foreground">Location and unit are filters: choose them above rather than typing them into the search.</p> : null}
      <Hint of={hits.data} />
      {hits.data?.has_more ? (
        <button type="button" className="mt-2 text-xs text-accent" onClick={() => address.write({ cursor: hits.data?.next_cursor ?? undefined })}>
          More…
        </button>
      ) : null}
    </>
  )
}

function Flows({ database, address }: { database: string; address: Address }) {
  const query = address.read('q')
  const compartment = address.read('compartment')
  const cursor = address.read('cursor') || undefined
  const compartments = useVocabulary(database, 'compartments')
  const hits = useSearchElementaryFlows(database, { query, compartment: compartment || undefined, limit: 25, cursor })
  return (
    <>
      <div className="pb-2">
        <Select id="search-compartment" label="Compartment" value={compartment} options={(compartments.data?.value ?? []).map((t) => t.value)} onChange={(v) => address.write({ compartment: v, cursor: undefined })} />
      </div>
      <DataTable<ElementaryFlowHit>
        columns={[
          { key: 'name', header: 'Name', render: (h) => h.name },
          { key: 'compartment', header: 'Compartment', render: (h) => (h.sub_compartment ? `${h.compartment} / ${h.sub_compartment}` : h.compartment) },
          { key: 'type', header: 'Type', render: (h) => h.flow_type },
          { key: 'unit', header: 'Unit', render: (h) => h.unit },
          { key: 'cas', header: 'CAS', render: (h) => h.cas_number ?? '' },
        ]}
        rows={hits.data?.items ?? []}
        rowKey={(h) => h.ref.id}
        empty={hits.error?.message ?? (query ? 'No match.' : 'Type a query.')}
      />
      {hits.data && hits.data.items.length === 0 ? <p className="pt-1 text-xs text-muted-foreground">Compartment is a filter: choose it above rather than typing it into the search.</p> : null}
      <Hint of={hits.data} />
      {hits.data?.has_more ? (
        <button type="button" className="mt-2 text-xs text-accent" onClick={() => address.write({ cursor: hits.data?.next_cursor ?? undefined })}>
          More…
        </button>
      ) : null}
    </>
  )
}

function Methods({ database, address }: { database: string; address: Address }) {
  const query = address.read('q')
  const cursor = address.read('cursor') || undefined
  const hits = useSearchMethods(database, { query, limit: 25, cursor })
  return (
    <>
      <DataTable<Method>
        columns={[
          { key: 'id', header: 'Id', render: (m) => <code>{m.id}</code> },
          { key: 'method', header: 'Impact method', render: (m) => m.impact_method },
          { key: 'category', header: 'Impact category', render: (m) => m.impact_category },
          { key: 'indicator', header: 'Indicator', render: (m) => m.indicator },
          { key: 'unit', header: 'Unit', render: (m) => m.unit },
        ]}
        rows={hits.data?.items ?? []}
        rowKey={(m) => m.id}
        empty={hits.error?.message ?? (query ? 'No match.' : 'Type a query.')}
      />
      <Hint of={hits.data} />
      {hits.data?.has_more ? (
        <button type="button" className="mt-2 text-xs text-accent" onClick={() => address.write({ cursor: hits.data?.next_cursor ?? undefined })}>
          More…
        </button>
      ) : null}
    </>
  )
}

function SearchBody({ name, kind }: { name: string; kind: SearchKind }) {
  const address = useAddress()
  const [typed, setTyped] = useState(address.read('q'))
  return (
    <>
      <form
        className="flex min-w-0 gap-2 pb-2"
        onSubmit={(e) => {
          e.preventDefault()
          address.write({ q: typed, cursor: undefined })
        }}
      >
        <input id="search-query" className="w-72 min-w-0 rounded-sm border bg-background px-1.5 py-0.5" placeholder="Search…" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <button type="submit" className="rounded-sm border px-2 text-xs">
          Search
        </button>
      </form>
      {kind === 'processes' ? <Processes database={name} address={address} /> : kind === 'elementary-flows' ? <Flows database={name} address={address} /> : <Methods database={name} address={address} />}
    </>
  )
}

function KnownSearch({ name, kind }: { name: string; kind: SearchKind }) {
  const location = useLocation()
  useEditorTab({ id: `search:${name}:${kind}`, kind: 'search', title: `${TITLES[kind]} · ${name}`, path: `${paths.search(name, kind)}${location.search}` })
  return (
    <>
      <EditorHeader icon="database" page={TITLES[kind]} entity={name} />
      <Section title="Search" sectionKey={`search:${name}:${kind}`}>
        <SearchBody key={`${name}:${kind}`} name={name} kind={kind} />
      </Section>
    </>
  )
}

function UnknownSearch({ name, kind }: { name: string; kind: string }) {
  return (
    <div className="p-3">
      <p>
        {name} has no search named “{kind}”. A background database is searched for:
      </p>
      <ul className="list-disc pl-5">
        {Object.entries(TITLES).map(([known, title]) => (
          <li key={known}>
            <AppLink to={paths.search(name, known)} className="text-primary hover:underline">
              {title}
            </AppLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function SearchEditor() {
  const { name = '', kind = 'processes' } = useParams()
  return isSearchKind(kind) ? <KnownSearch name={name} kind={kind} /> : <UnknownSearch name={name} kind={kind} />
}
