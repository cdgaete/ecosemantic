import { useMatch } from 'react-router-dom'
import { useLog } from '@/api/queries'
import type { ProductSystem } from '@/api/types'
import { useUi, type ChosenEntry } from '@/store/ui'

export type CanvasState = { live: true } | { live: false; hash: string; entry: ChosenEntry | null }

export interface CanvasVariant {
  kind: 'case' | 'scenario'
  name: string
}

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

/** The case or the scenario `system` holds under `name`, or null when it holds neither. */
export function heldVariant(system: ProductSystem, name: string | null): CanvasVariant | null {
  if (name === null) return null
  if (system.cases.some((one) => one.name === name)) return { kind: 'case', name }
  if (system.scenarios.some((one) => one.name === name)) return { kind: 'scenario', name }
  return null
}

export function useCanvasVariant(system: ProductSystem | undefined): CanvasVariant | null {
  const chosen = useUi((s) => (system === undefined || s.canvasSystemId !== system.id ? null : s.canvasVariant))
  const state = useCanvasState(system?.id ?? null)
  if (system === undefined || chosen === null || !state.live) return null
  return heldVariant(system, chosen)
}
