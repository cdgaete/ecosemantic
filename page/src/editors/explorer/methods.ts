import type { Method, MethodCategory, MethodFamily } from '@/api/types'

export interface Found {
  family: MethodFamily
  category: MethodCategory
  method: Method
}

export function findIndicator(families: MethodFamily[], id: string): Found | null {
  for (const family of families) {
    for (const category of family.categories) {
      const method = category.indicators.find((entry) => entry.id === id)
      if (method !== undefined) return { family, category, method }
    }
  }
  return null
}
