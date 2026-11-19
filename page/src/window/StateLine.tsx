import type { CanvasVariant } from './useCanvasState'

export function StateLine({ state }: { state: CanvasVariant | null }) {
  if (state === null) return null
  return <p className="text-xs text-muted-foreground">{`Under ${state.kind} ${state.name}`}</p>
}

export function StateRefused({ state, message }: { state: CanvasVariant; message: string }) {
  return <p className="p-4 text-destructive">{`${state.kind} ${state.name} cannot be read: ${message}`}</p>
}
