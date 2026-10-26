import { useState } from 'react'
import { useDatabases, useInstalls, useSources } from '@/api/queries'
import type { Database, Install, SourceName } from '@/api/types'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import { InstallStatus } from './InstallStatus'
import { SourceForm } from './SourceForm'
import { SourceList } from './SourceList'

const COLUMNS: Column<Database>[] = [
  { key: 'name', header: 'Name', render: (db) => db.name },
  { key: 'version', header: 'Version', render: (db) => db.version },
  { key: 'model', header: 'System model', render: (db) => db.system_model },
  { key: 'scheme', header: 'Scheme', render: (db) => db.scheme },
  {
    key: 'fingerprint',
    header: 'Fingerprint',
    render: (db) => <span className="tabular-nums [overflow-wrap:anywhere]">{db.fingerprint === null ? '–' : db.fingerprint.slice(0, 12)}</span>,
  },
]

function Settled({ install }: { install: Install }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border bg-background px-2 py-1 text-xs">
      <span className="flex flex-wrap items-center gap-x-3">
        <span className="font-medium">
          {install.draft.source} {install.draft.version ?? ''}
        </span>
        <span className="text-muted-foreground">{install.status}</span>
      </span>
      {install.error === null ? null : <p className="text-destructive">{install.error.message}</p>}
    </div>
  )
}

export function DatabasesEditor() {
  const databases = useDatabases()
  const sources = useSources()
  const installs = useInstalls()
  const [picked, setPicked] = useState<SourceName | null>(null)
  const listed = installs.data?.value ?? []
  const open = listed.filter((install) => install.open)
  const settled = listed.find((install) => !install.open) ?? null
  const source = sources.data?.value.find((candidate) => candidate.name === picked) ?? null
  const terms = picked === null ? null : (listed.find((install) => install.draft.source === picked && install.status === 'terms') ?? null)
  return (
    <>
      <EditorHeader icon="database" page="Databases" entity="sources and installs" />
      <Section title="Installed databases" sectionKey="databases:installed">
        {databases.error ? <p className="text-destructive">{databases.error.message}</p> : null}
        <DataTable columns={COLUMNS} rows={databases.data?.value ?? []} rowKey={(db) => db.name} empty="No background database is installed yet." />
      </Section>
      <Section title="Sources" sectionKey="databases:sources">
        {sources.error ? <p className="text-destructive">{sources.error.message}</p> : null}
        <SourceList sources={sources.data?.value ?? []} picked={picked} onPick={setPicked} />
        {source === null ? (
          <p className="pt-2 text-xs text-muted-foreground">Pick a source to install a database from.</p>
        ) : (
          <SourceForm key={source.name} source={source} terms={terms} />
        )}
      </Section>
      <Section title="Installs" sectionKey="databases:installs">
        {open.length === 0 && settled === null ? <p className="text-xs text-muted-foreground">No install has been posted.</p> : null}
        {open.map((install) => (
          <InstallStatus key={install.id} install={install} />
        ))}
        {settled === null ? null : <Settled install={settled} />}
      </Section>
    </>
  )
}
