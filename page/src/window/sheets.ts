import { useCallback } from 'react'
import { matchPath, useLocation } from 'react-router-dom'
import { RESULT_PAGES } from '@/editors/results/pages'
import { databaseOfPath, paths, useGo } from '@/lib/paths'
import { useUi, type SheetKind } from '@/store/ui'

export interface Place {
  address: string
  kind: SheetKind | null
}

export interface SheetReturn {
  kind: SheetKind
  to: string
  label: string
  docked: boolean
}

function pathOf(address: string): string {
  return address.split('?')[0]
}

/** The system an address is under, and null for an address under none. */
export function systemOf(address: string): string | null {
  return matchPath('/systems/:id/*', pathOf(address))?.params.id ?? null
}

/** Whether an address is a page of an open result, which docks under the graph instead of opening a sheet. */
export function dockedOf(pathname: string): boolean {
  const page = matchPath('/systems/:id/results/:page', pathname)?.params.page
  return page !== undefined && RESULT_PAGES.some((entry) => entry.key === page)
}

/** The sheet an address opens: the explorer under one database, the results on a page of an open result or on a simulation, and none anywhere else. */
export function sheetOf(pathname: string): SheetKind | null {
  if (databaseOfPath(pathname) !== null) return 'explorer'
  if (dockedOf(pathname)) return 'results'
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
 * a result is under or the canvas holds, else the product systems. Null where the address opens no sheet. A page of an
 * open result is answered at every width and docked, the graph staying beside it; the explorer and a simulation are
 * sheets.
 */
export function useSheet(): SheetReturn | null {
  const { pathname } = useLocation()
  const kind = sheetOf(pathname)
  const origin = useUi((s) => (kind === null ? null : s.origins[kind]))
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  if (kind === null) return null
  const system = kind === 'results' ? systemOf(pathname) : canvasSystemId
  const to = origin ?? (system === null ? paths.home() : paths.system(system))
  return { kind, to, label: returnLabel(to), docked: dockedOf(pathname) }
}

/** The way out of an open sheet, wherever it is left from: the address it was opened at, or the one it falls back to. */
export function useLeaveSheet(): () => void {
  const go = useGo()
  const to = useSheet()?.to ?? null
  return useCallback(() => {
    if (to !== null) go(to)
  }, [go, to])
}
