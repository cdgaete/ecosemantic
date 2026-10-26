import { FileText, History, PanelRightOpen } from 'lucide-react'
import { paths, useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { IconButton } from './IconButton'

export function PanelRail({ systemId }: { systemId: string }) {
  const go = useGo()
  const details = useUi((s) => s.details)
  const lastDetails = useUi((s) => s.lastDetails)
  const setPanelMode = useUi((s) => s.setPanelMode)
  const open = (path: string) => {
    setPanelMode('beside')
    go(path)
  }
  return (
    <div role="toolbar" aria-label="Panel" aria-orientation="vertical" className="flex w-10 flex-col items-center gap-1 border-l bg-chrome py-1.5">
      <IconButton label="Show panel" shortcut="panel" side="left" onClick={() => setPanelMode('beside')}>
        <PanelRightOpen />
      </IconButton>
      <IconButton label="Show Activity" side="left" onClick={() => open(paths.system(systemId))}>
        <History />
      </IconButton>
      <IconButton label="Show Details" side="left" onClick={() => open(details?.path ?? lastDetails?.path ?? paths.systemPage(systemId, 'general'))}>
        <FileText />
      </IconButton>
    </div>
  )
}
