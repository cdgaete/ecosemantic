import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useReleaseCards, useSystem } from '@/api/queries'
import { useResultParams } from '@/editors/results/useResultParams'
import { useGo } from '@/lib/paths'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useFiles } from './files'
import { closeInspector, openInspector, toggleWidened, useInspectorShown } from './inspector'
import { menus, type Menu } from './menus'
import { openNavigation } from './navigation'
import { runCanvas } from './shortcuts'

export function useMenus(): { menus: Menu[]; dialog: ReactNode; go: (path: string) => void } {
  const go = useGo()
  const location = useLocation()
  const systemId = useUi((s) => s.canvasSystemId)
  const variant = useUi((s) => s.canvasVariant)
  const theme = useUi((s) => s.theme)
  const setTheme = useUi((s) => s.setTheme)
  const inspector = useUi((s) => s.inspector)
  const inspectorShown = useInspectorShown()
  const openRequest = useRequestDialog((s) => s.open)
  const read = useSystem(systemId ?? '', systemId !== null)
  const resolved = useResultParams(systemId ?? '', location.search)
  const files = useFiles()
  const release = useReleaseCards(systemId ?? '', variant)
  const onResult = systemId !== null && location.pathname.startsWith(`/systems/${systemId}/results/`) && !location.pathname.endsWith('/setup')
  const all = menus({
    systemId,
    resultOpen: onResult && resolved.params !== null,
    openRequests: read.data?.open_requests ?? 0,
    theme,
    openNavigation,
    importFile: files.importFile,
    downloadResult: files.downloadResult,
    inspector,
    inspectorShown,
    openInspector,
    closeInspector,
    toggleWidened,
    setTheme,
    newRequest: () => systemId && openRequest({ systemId }),
    reorganise: () => runCanvas('reorganise'),
    resetLayout: () => release.mutate(),
  })
  return { menus: all, dialog: files.dialog, go }
}
