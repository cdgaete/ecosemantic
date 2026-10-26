import { MessageSquare } from 'lucide-react'
import type { Entity } from '@/api/types'
import { useRequestDialog } from './useRequestDialog'

export function RequestAction({ systemId, entity, entityId }: { systemId: string; entity?: Entity; entityId?: string }) {
  const open = useRequestDialog((s) => s.open)
  return (
    <button type="button" className="flex items-center gap-1 rounded-sm border border-primary px-2 py-0.5 text-xs text-primary" onClick={() => open({ systemId, entity, entityId })}>
      <MessageSquare className="size-3" />
      Request
    </button>
  )
}
