import { useMatch } from 'react-router-dom'
import { useLog } from '@/api/queries'
import { useUi, type ChosenEntry } from '@/store/ui'

export type CanvasState = { live: true } | { live: false; hash: string; entry: ChosenEntry | null }

export function useCanvasState(systemId: string | null): CanvasState {
  const version = useMatch('/systems/:id/versions/:hash/*')
  const chosen = useUi((s) => s.chosenEntry)
  const log = useLog(systemId ?? '', systemId !== null)
  const hash = version !== null && version.params.id === systemId ? (version.params.hash ?? null) : null
  const latest = log.data?.value.at(-1)?.seq ?? null
  if (systemId === null) return { live: true }
  if (hash !== null) return { live: false, hash, entry: null }
  if (chosen !== null && chosen.systemId === systemId && latest !== null && chosen.seq < latest) return { live: false, hash: chosen.hash, entry: chosen }
  return { live: true }
}
