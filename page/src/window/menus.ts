import { api } from '@/api/client'
import { paths } from '@/lib/paths'
import type { InspectorMode, Theme } from '@/store/ui'

export interface MenuItem {
  key: string
  label: string
  disabled?: boolean
  href?: string
  to?: string
  run?: () => void
  items?: MenuItem[]
}

export interface Menu {
  key: string
  label: string
  items: MenuItem[]
}

export type Format = 'tables' | 'openlca'
export type ResultKind = 'impact' | 'contributions' | 'inventory'

export interface MenuContext {
  systemId: string | null
  resultOpen: boolean
  openRequests: number
  theme: Theme
  openNavigation: () => void
  importFile: (format: Format) => void
  downloadResult: (kind: ResultKind) => void
  inspector: InspectorMode
  inspectorShown: boolean
  openInspector: () => void
  closeInspector: () => void
  toggleWidened: () => void
  setTheme: (theme: Theme) => void
  newRequest: () => void
  reorganise: () => void
  resetLayout: () => void
}

export function menus(context: MenuContext): Menu[] {
  const id = context.systemId
  const none = id === null
  const system = id ?? ''
  return [
    {
      key: 'file',
      label: 'File',
      items: [
        { key: 'all-systems', label: 'All product systems', to: paths.home() },
        { key: 'open', label: 'Open product system…', run: context.openNavigation },
        {
          key: 'export',
          label: 'Export',
          disabled: none,
          items: [
            { key: 'export-tables', label: 'Tables (CSV + YAML)', href: api.tablesUrl(system) },
            { key: 'export-openlca', label: 'openLCA package', href: api.packageUrl(system) },
          ],
        },
        {
          key: 'import',
          label: 'Import',
          disabled: none,
          items: [
            { key: 'import-tables', label: 'Tables…', run: () => context.importFile('tables') },
            { key: 'import-openlca', label: 'openLCA package…', run: () => context.importFile('openlca') },
          ],
        },
      ],
    },
    {
      key: 'calculate',
      label: 'Calculate',
      items: [
        { key: 'impact', label: 'Impact result…', disabled: none, to: paths.results(system, 'setup', '') },
        { key: 'simulation', label: 'Monte Carlo simulation…', disabled: none, to: paths.results(system, 'setup', '?kind=simulation') },
        { key: 'results', label: 'All results', disabled: none, to: paths.resultList(system) },
        {
          key: 'download',
          label: 'Download result as files',
          disabled: none || !context.resultOpen,
          items: [
            { key: 'download-impact', label: 'Impact', run: () => context.downloadResult('impact') },
            { key: 'download-contributions', label: 'Contributions', run: () => context.downloadResult('contributions') },
            { key: 'download-inventory', label: 'Inventory', run: () => context.downloadResult('inventory') },
          ],
        },
      ],
    },
    {
      key: 'view',
      label: 'View',
      items: [
        { key: 'activity', label: 'Activity', disabled: none, to: paths.system(system) },
        { key: 'details', label: 'Details', disabled: none, to: paths.systemPage(system, 'general') },
        {
          key: 'inspector',
          label: 'Inspector',
          disabled: none,
          items: [
            { key: 'inspector-open', label: 'Open', disabled: context.inspectorShown, run: context.openInspector },
            { key: 'inspector-widen', label: context.inspector === 'widened' ? 'Return to width' : 'Widen', run: context.toggleWidened },
            { key: 'inspector-close', label: 'Close', disabled: !context.inspectorShown, run: context.closeInspector },
          ],
        },
        { key: 'navigation', label: 'Navigation', run: context.openNavigation },
        { key: 'reorganise', label: 'Reorganise the graph', disabled: none, run: context.reorganise },
        { key: 'reset-layout', label: 'Reset layout', disabled: none, run: context.resetLayout },
        {
          key: 'theme',
          label: 'Theme',
          items: [
            { key: 'theme-light', label: context.theme === 'light' ? '✓ Light' : 'Light', run: () => context.setTheme('light') },
            { key: 'theme-dark', label: context.theme === 'dark' ? '✓ Dark' : 'Dark', run: () => context.setTheme('dark') },
          ],
        },
      ],
    },
    {
      key: 'requests',
      label: 'Requests',
      items: [
        { key: 'new-request', label: 'New request…', disabled: none, run: context.newRequest },
        { key: 'open-requests', label: `Open requests (${context.openRequests})`, disabled: none, to: paths.systemPage(system, 'requests') },
      ],
    },
  ]
}
