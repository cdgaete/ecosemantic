import { useEffect } from 'react'
import { reconnect, useLive, watchWaiting, type Connection } from '@/api/stream'
import { formatAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'

const SAID: Record<Connection, string> = { open: 'Live', connecting: 'Connecting…', retrying: 'Reconnecting…', closed: 'Disconnected' }
const DOT: Record<Connection, string> = { open: 'bg-success', connecting: 'bg-warning', retrying: 'bg-warning', closed: 'bg-destructive' }

export function LiveStatus() {
  const connection = useLive((s) => s.connection)
  const systemId = useUi((s) => s.canvasSystemId)
  const latest = useLive((s) => (systemId === null ? undefined : s.latest[systemId]))
  const blocked = useLive((s) => s.blocked)
  const streams = useLive((s) => s.streams)
  useEffect(() => {
    const timer = window.setInterval(watchWaiting, 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <span className="flex items-center gap-2">
      <span className={cn('inline-block size-2 rounded-full', DOT[connection])} />
      {SAID[connection]}
      {latest ? (
        <span title={latest.timestamp}>
          {' '}· entry #{latest.seq} {formatAgo(latest.timestamp)}
        </span>
      ) : null}
      {blocked ? <span className="text-warning">{`Waiting on a connection slot: this browser holds ${streams} event stream${streams === 1 ? '' : 's'}`}</span> : null}
      {connection === 'closed' ? (
        <button type="button" className="text-accent underline" onClick={reconnect}>
          Reconnect
        </button>
      ) : null}
    </span>
  )
}
