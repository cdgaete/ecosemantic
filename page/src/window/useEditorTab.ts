import { useEffect } from 'react'
import { useUi, type EditorTab } from '@/store/ui'

export function useEditorTab(tab: EditorTab | null): void {
  const showDetails = useUi((s) => s.showDetails)
  const showActivity = useUi((s) => s.showActivity)
  const id = tab?.id
  const kind = tab?.kind
  const title = tab?.title
  const path = tab?.path
  useEffect(() => {
    if (id === undefined || kind === undefined || title === undefined || path === undefined) showActivity()
    else showDetails({ id, kind, title, path })
  }, [showDetails, showActivity, id, kind, title, path])
}
