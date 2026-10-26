import { useSearchParams } from 'react-router-dom'

export type Patch = Record<string, string | undefined>

export interface Address {
  read: (key: string) => string
  write: (patch: Patch) => void
}

export function useAddress(): Address {
  const [search, setSearch] = useSearchParams()
  return {
    read: (key) => search.get(key) ?? '',
    write: (patch) => {
      const next = new URLSearchParams(search)
      for (const [key, value] of Object.entries(patch)) {
        if (value === undefined || value === '') next.delete(key)
        else next.set(key, value)
      }
      setSearch(next, { replace: true })
    },
  }
}

export function useCategory<T extends { method: { id: string } }>(categories: T[]): { chosen: T | undefined; choose: (id: string) => void } {
  const address = useAddress()
  const named = address.read('category')
  return {
    chosen: categories.find((c) => c.method.id === named) ?? categories[0],
    choose: (id) => address.write({ category: id }),
  }
}
