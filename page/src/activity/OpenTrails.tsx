import { useAgents, useOpenTrail } from '@/api/queries'
import { formatAgo } from '@/lib/format'
import { colourOf } from './agents'
import { Trail } from './Trail'

const QUIET_AFTER = 5 * 60_000

function OpenTrail({ agent, systemId, lastCallAt }: { agent: string; systemId: string; lastCallAt: string }) {
  const read = useOpenTrail(agent, systemId)
  const calls = read.data?.value ?? []
  if (calls.length === 0) return null
  const quiet = Date.now() - new Date(lastCallAt).getTime() > QUIET_AFTER
  return (
    <li className="border-l-2 py-1 pl-2" style={{ borderLeftColor: colourOf(agent) }}>
      <p className="text-xs font-medium" title={lastCallAt}>
        {agent} · {quiet ? `last active ${formatAgo(lastCallAt)}` : 'work in progress'}
      </p>
      <Trail calls={calls} />
    </li>
  )
}

export function OpenTrails({ systemId }: { systemId: string }) {
  const agents = useAgents()
  const working = (agents.data?.value ?? []).filter((a) => a.origin === 'agent' && a.product_system_id === systemId)
  if (working.length === 0) return null
  return (
    <ul aria-label="Work in progress" className="px-4 pt-2">
      {working.map((a) => (
        <OpenTrail key={a.agent} agent={a.agent} systemId={systemId} lastCallAt={a.last_call_at} />
      ))}
    </ul>
  )
}
