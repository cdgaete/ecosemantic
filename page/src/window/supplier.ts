import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { withoutToken } from '@/api/client'
import { useGo } from '@/lib/paths'

export interface SupplierOrigin {
  address: string
  name: string
  scroll: number
  exchange: string
  under: SupplierOrigin | null
}

export interface FollowedExchange {
  scroll: number
  exchange: string
}

const SCROLL_BODY = '[data-scroll-body]'

function isOrigin(value: unknown): value is SupplierOrigin {
  if (typeof value !== 'object' || value === null) return false
  const at = value as Partial<SupplierOrigin>
  const kept = typeof at.address === 'string' && typeof at.name === 'string' && typeof at.scroll === 'number' && typeof at.exchange === 'string'
  return kept && (at.under === null || isOrigin(at.under))
}

function isFollowed(value: unknown): value is FollowedExchange {
  if (typeof value !== 'object' || value === null) return false
  const at = value as Partial<FollowedExchange>
  return typeof at.scroll === 'number' && typeof at.exchange === 'string'
}

function supplierState(state: unknown): { from: SupplierOrigin | null; followed: FollowedExchange | null } {
  const held = (typeof state === 'object' && state !== null ? state : {}) as { supplierOrigin?: unknown; supplierReturn?: unknown }
  return {
    from: isOrigin(held.supplierOrigin) ? held.supplierOrigin : null,
    followed: isFollowed(held.supplierReturn) ? held.supplierReturn : null,
  }
}

/** The supplier a detail was followed from, and null for a detail opened at its own address. */
export function useSupplierOrigin(): SupplierOrigin | null {
  return supplierState(useLocation().state).from
}

/** The exchange a detail was returned to, and null for a detail opened at its own address. */
export function useFollowedExchange(): FollowedExchange | null {
  return supplierState(useLocation().state).followed
}

/** The state a page tab of this address carries on: the supplier origin, and nothing of the exchange a detail returned to. */
export function tabState(state: unknown): Record<string, unknown> {
  const { from } = supplierState(state)
  return from === null ? {} : { supplierOrigin: from }
}

export type FollowSupplier = (to: string, exchange: string, from: Element) => void

/**
 * The way to a supplier from a page of the process named `name`. The origin keeps its address, its name, the scroll of
 * its body and the exchange followed, beside the origin that page itself holds.
 */
export function useFollowSupplier(name: string): FollowSupplier {
  const { pathname, search, state } = useLocation()
  const { from } = supplierState(state)
  const go = useGo()
  return useCallback(
    (to: string, exchange: string, at: Element) => {
      const body = at.closest(SCROLL_BODY)
      const scroll = body instanceof HTMLElement ? body.scrollTop : 0
      const origin: SupplierOrigin = { address: withoutToken(`${pathname}${search}`), name, scroll, exchange, under: from }
      go(to, { supplierOrigin: origin })
    },
    [go, pathname, search, name, from],
  )
}
