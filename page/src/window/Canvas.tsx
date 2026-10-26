import { useMatch } from 'react-router-dom'
import { useLog, useSystem, useVersion } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import { GraphPage } from '@/editors/system/GraphPage'
import { useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'

function VersionCanvas({ id, hash }: { id: string; hash: string }) {
  const read = useVersion(id, hash)
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  return <GraphPage view={{ id, system: read.data, openRequests: 0, version: hash }} />
}

function LiveCanvas({ id }: { id: string }) {
  const go = useGo()
  useSystemStream(id, go)
  const read = useSystem(id)
  const log = useLog(id)
  const chosen = useUi((s) => s.chosenEntry)
  const choose = useUi((s) => s.chooseEntry)
  const latest = log.data?.value.at(-1)?.seq ?? null
  if (chosen !== null && chosen.systemId === id && latest !== null && chosen.seq < latest)
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-2 border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">
          <span>Read-only: the product system as it was at entry #{chosen.seq}.</span>
          <button type="button" className="underline" onClick={() => choose(null)}>
            Back to latest
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <VersionCanvas id={id} hash={chosen.hash} />
        </div>
      </div>
    )
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  return <GraphPage view={{ id, system: read.data.value, openRequests: read.data.open_requests, version: null }} />
}

export function Canvas({ systemId }: { systemId: string }) {
  const version = useMatch('/systems/:id/versions/:hash/*')
  const hash = version?.params.id === systemId ? (version.params.hash ?? null) : null
  return hash ? <VersionCanvas id={systemId} hash={hash} /> : <LiveCanvas id={systemId} />
}
