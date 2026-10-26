import { useState } from 'react'
import { usePostRequest } from '@/api/queries'
import type { Entity, RequestKind } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Icon } from '@/window/Icon'
import { useUi } from '@/store/ui'

const ENTITY_ICON: Record<Entity, 'system' | 'process' | 'product' | 'parameter'> = {
  product_system: 'system',
  process: 'process',
  exchange: 'product',
  parameter: 'parameter',
  case: 'parameter',
  scenario: 'parameter',
}

export function RequestForm({ systemId, atHash, entity, entityId, onDone }: { systemId: string; atHash: string; entity?: Entity; entityId?: string; onDone: () => void }) {
  const person = useUi((s) => s.person)
  const setPerson = useUi((s) => s.setPerson)
  const [name, setName] = useState(person ?? '')
  const named = entity !== undefined && entityId !== undefined
  const [kind, setKind] = useState<RequestKind>(named ? 'edit' : 'return')
  const [message, setMessage] = useState('')
  const post = usePostRequest(systemId)
  const kinds: RequestKind[] = named ? ['edit', 'return', 'approve'] : ['return', 'approve']
  const submit = async () => {
    if (!person) setPerson(name)
    await post.mutateAsync({
      actor: person ?? name,
      kind,
      at_hash: atHash,
      message,
      ...(kind === 'edit' && named ? { entity, entity_id: entityId } : {}),
    })
    onDone()
  }
  return (
    <form
      className="grid max-w-xl grid-cols-[110px_minmax(0,1fr)] items-center gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      {person ? null : (
        <>
          <label htmlFor="request-name">Your name</label>
          <input id="request-name" className="rounded-sm border bg-background px-1.5 py-0.5" value={name} onChange={(e) => setName(e.target.value)} required />
        </>
      )}
      <label htmlFor="request-kind">Kind</label>
      <select id="request-kind" className="rounded-sm border bg-background px-1.5 py-0.5" value={kind} onChange={(e) => setKind(e.target.value as RequestKind)}>
        {kinds.map((k) => (
          <option key={k} value={k}>
            {k}
          </option>
        ))}
      </select>
      {named ? (
        <>
          <span>Entity</span>
          <span className="flex items-center gap-1.5">
            <Icon name={ENTITY_ICON[entity]} />
            {entity} · {entityId}
          </span>
        </>
      ) : null}
      <label htmlFor="request-message">Message</label>
      <textarea id="request-message" className="min-h-16 rounded-sm border bg-background px-1.5 py-0.5" value={message} onChange={(e) => setMessage(e.target.value)} required />
      <span />
      <span className="flex items-center gap-3">
        <Button type="submit" size="sm" disabled={post.isPending}>
          Post request
        </Button>
        <span className="text-xs text-muted-foreground">Posted at the hash you are looking at. The agent sees the count on its next write or read.</span>
      </span>
      {post.error ? <p className="col-span-2 text-destructive">{post.error.message}</p> : null}
    </form>
  )
}
