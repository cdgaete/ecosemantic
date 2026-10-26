import { useRequests } from '@/api/queries'
import type { Request } from '@/api/types'
import { shortHash } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { RequestForm } from '@/requests/RequestForm'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import type { SystemView } from './SystemEditor'

function Row({ request }: { request: Request }) {
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 border-b py-1.5">
      <span className="font-semibold capitalize">
        {request.kind}
        {request.open ? <span className="ml-2 rounded-full bg-warning/15 px-1.5 text-xs font-medium text-warning">open</span> : null}
      </span>
      <span>
        {request.entity ? (
          <b>
            {request.entity} · {request.entity_id} —{' '}
          </b>
        ) : null}
        {request.message}
      </span>
      <span className="text-xs text-muted-foreground">#{request.seq}</span>
      <span className="text-xs text-muted-foreground">
        {request.actor.name} · {request.timestamp} · at {shortHash(request.at_hash)}
      </span>
      {request.outcome ? (
        <span className="col-start-2 border-l-2 border-success pl-2 text-xs">
          <b>{request.outcome.resolution}</b> · {request.outcome.actor.kind} · {request.outcome.timestamp} — {request.outcome.message}
        </span>
      ) : null}
    </li>
  )
}

export function RequestsPage({ view }: { view: SystemView }) {
  const requests = useRequests(view.id)
  const rows = [...(requests.data?.value ?? [])].reverse()
  return (
    <>
      <EditorHeader icon="request" page="Requests" entity={view.system.name} />
      <Section title="Requests" sectionKey={`system:${view.id}:requests`} actions={view.version ? undefined : <RequestAction systemId={view.id} entity="product_system" entityId={view.system.id} />}>
        {requests.error ? <p className="text-destructive">{requests.error.message}</p> : null}
        <ul>
          {rows.map((r) => (
            <Row key={r.id} request={r} />
          ))}
        </ul>
        {rows.length === 0 ? <p className="text-muted-foreground">No request yet.</p> : null}
      </Section>
      {view.version ? null : (
        <Section title="New request" sectionKey={`system:${view.id}:new-request`}>
          {view.system.hash === null ? (
            <p className="text-warning">The stored product system carries no hash yet.</p>
          ) : (
            <RequestForm systemId={view.id} atHash={view.system.hash} onDone={() => undefined} />
          )}
        </Section>
      )}
    </>
  )
}
