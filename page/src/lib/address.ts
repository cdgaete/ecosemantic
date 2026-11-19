import { useLocation, useSearchParams } from 'react-router-dom'
import { useUi } from '@/store/ui'

export type Patch = Record<string, string | undefined>

export interface Address {
  read: (key: string) => string
  write: (patch: Patch) => void
  href: (patch: Patch) => string
}

function patched(search: URLSearchParams, patch: Patch): URLSearchParams {
  const next = new URLSearchParams(search)
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined || value === '') next.delete(key)
    else next.set(key, value)
  }
  return next
}

export function useAddress(): Address {
  const [search, setSearch] = useSearchParams()
  const location = useLocation()
  return {
    read: (key) => search.get(key) ?? '',
    write: (patch) => setSearch(patched(search, patch), { replace: true }),
    href: (patch) => {
      const text = patched(search, patch).toString()
      return text ? `${location.pathname}?${text}` : location.pathname
    },
  }
}

export function useCategory<T extends { method_id: string }>(
  categories: T[],
  systemId: string,
  score?: (category: T) => number,
): { chosen: T | undefined; choose: (id: string) => void } {
  const address = useAddress()
  const remembered = useUi((state) => state.resultCategories[systemId])
  const remember = useUi((state) => state.setResultCategory)
  const named = address.read('category')
  const chosen =
    categories.find((category) => category.method_id === named) ??
    categories.find((category) => category.method_id === remembered) ??
    (score === undefined ? undefined : categories.find((category) => score(category) !== 0)) ??
    categories[0]
  const choose = (id: string) => {
    address.write({ category: id })
    remember(systemId, id)
  }
  return { chosen, choose }
}
