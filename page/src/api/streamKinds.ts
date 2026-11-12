import type { EventKind } from './types'

export const STREAM_KINDS = ['entry', 'layout', 'request', 'resolution', 'run', 'install', 'deleted', 'call'] as const satisfies readonly EventKind[]
