import { useSystem, useVersion } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import { GraphPage } from '@/editors/system/GraphPage'
import { useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { InSlot } from './slots'
import { useCanvasState } from './useCanvasState'

function FollowSystem({ id }: { id: string }) {
  const go = useGo()
  useSystemStream(id, go)
  return null
}

function VersionCanvas({ id, hash }: { id: string; hash: string }) {
  const read = useVersion(id, hash)
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  return <GraphPage view={{ id, system: read.data, openRequests: 0, version: hash }} />
}

function LiveCanvas({ id }: { id: string }) {
  const read = useSystem(id)
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  return <GraphPage view={{ id, system: read.data.value, openRequests: read.data.open_requests, version: null }} />
}

export function Canvas({ systemId }: { systemId: string }) {
  const shown = useCanvasState(systemId)
  const choose = useUi((s) => s.chooseEntry)
  const entry = shown.live ? null : shown.entry
  const followed = shown.live || entry !== null
  return (
    <>
      {followed ? <FollowSystem id={systemId} /> : null}
      {shown.live ? (
        <LiveCanvas id={systemId} />
      ) : (
        <>
          {entry === null ? null : (
            <InSlot name="notice">
              <div role="status" className="flex items-center justify-between gap-2 rounded-xl border border-warning bg-warning/10 px-3 py-1 text-xs text-warning shadow-lg">
                <span>Read-only: the product system as it was at entry #{entry.seq}.</span>
                <button type="button" className="underline" onClick={() => choose(null)}>
                  Back to latest
                </button>
              </div>
            </InSlot>
          )}
          <VersionCanvas id={systemId} hash={shown.hash} />
        </>
      )}
    </>
  )
}
