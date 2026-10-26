import { paths } from '@/lib/paths'
import type { PageTab } from '@/window/PageTabs'

export const SYSTEM_PAGES = ['general', 'parameters', 'statistics', 'requests', 'simulations']

export function systemPages(id: string, hash: string | null = null): PageTab[] {
  if (hash !== null) {
    const base = paths.version(id, hash)
    return [
      { key: 'general', label: 'General information', path: base },
      { key: 'parameters', label: 'Parameters', path: `${base}/parameters` },
      { key: 'statistics', label: 'Statistics', path: `${base}/statistics` },
    ]
  }
  return [
    { key: 'general', label: 'General information', path: paths.systemPage(id, 'general') },
    { key: 'parameters', label: 'Parameters', path: paths.systemPage(id, 'parameters') },
    { key: 'statistics', label: 'Statistics', path: paths.systemPage(id, 'statistics') },
    { key: 'requests', label: 'Requests', path: paths.systemPage(id, 'requests') },
    { key: 'simulations', label: 'Simulations', path: paths.systemPage(id, 'simulations') },
  ]
}
