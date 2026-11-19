import { matchPath, useLocation } from 'react-router-dom'
import { RESULT_PAGES } from '@/editors/results/pages'
import { databaseOfPath, paths } from '@/lib/paths'
import { useUi, type SheetKind } from '@/store/ui'
import { NARROW_BELOW } from './inspector'
import { useMinWidth } from './useMinWidth'

export interface Place {
  address: string
  kind: SheetKind | null
}

export interface SheetReturn {
  kind: SheetKind
  to: string
  label: string
}

function pathOf(address: string): string {
  return address.split('?')[0]
}

/** The system an address is under, and null for an address under none. */
export function systemOf(address: string): string | null {
  return matchPath('/systems/:id/*', pathOf(address))?.params.id ?? null
}

/** The sheet an address opens: the explorer under one database, the results on a page of an open result or on a simulation, and none anywhere else. */
export function sheetOf(pathname: string): SheetKind | null {
  if (databaseOfPath(pathname) !== null) return 'explorer'
  const page = matchPath('/systems/:id/results/:page', pathname)?.params.page
  if (page !== undefined && RESULT_PAGES.some((entry) => entry.key === page)) return 'results'
  return matchPath('/systems/:id/simulations/:runId', pathname) === null ? null : 'results'
}

/**
 * The origin a sheet takes when the address moves from one place to the next, and undefined when it keeps the one it has.
 * A sheet keeps its origin while the person moves inside it and when they come back into it from a sheet opened over it;
 * opened at its own address it has none.
 */
export function originAfter(before: Place | null, here: Place, origins: Record<SheetKind, string | null>): string | null | undefined {
  if (here.kind === null) return undefined
  if (before === null) return null
  if (before.kind === here.kind) return undefined
  const under = before.kind === null ? null : origins[before.kind]
  if (under !== null && sheetOf(pathOf(under)) === here.kind) return undefined
  return before.address
}

export function returnLabel(address: string): string {
  const pathname = pathOf(address)
  if (systemOf(address) !== null) return 'Back to graph'
  if (databaseOfPath(pathname) !== null) return 'Back to the explorer'
  if (pathname === paths.home()) return 'Back to product systems'
  if (pathname === paths.databases()) return 'Back to databases'
  return 'Back'
}

/**
 * The sheet drawn over the page and the address it is left to: where it was opened from, else the graph of the system
 * a result is under or the canvas holds, else the product systems. Null where the address opens no sheet, and for the
 * results below 768 px, where the inspector's own sheet holds them.
 */
export function useSheet(): SheetReturn | null {
  const { pathname } = useLocation()
  const kind = sheetOf(pathname)
  const origin = useUi((s) => (kind === null ? null : s.origins[kind]))
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  const narrow = !useMinWidth(NARROW_BELOW)
  if (kind === null || (kind === 'results' && narrow)) return null
  const system = kind === 'results' ? systemOf(pathname) : canvasSystemId
  const to = origin ?? (system === null ? paths.home() : paths.system(system))
  return { kind, to, label: returnLabel(to) }
}
