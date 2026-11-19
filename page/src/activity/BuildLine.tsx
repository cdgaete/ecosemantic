import { PanelRightOpen, SlidersHorizontal, Plus } from 'lucide-react'
import { useLog } from '@/api/queries'
import { formatAgo } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { openInspector } from '@/window/inspector'
import { IconButton } from '@/window/IconButton'
import { CalculateButton } from '@/editors/system/CalculateButton'
import { actorOf } from './agents'
import { Message } from './Message'

interface BuildLineProps {
  systemId: string
  live: boolean
  toolsOpen: boolean
  onTools: () => void
}

export function BuildLine({ systemId, live, toolsOpen, onTools }: BuildLineProps) {
  const log = useLog(systemId)
  const go = useGo()
  const held = useUi((s) => (s.sheetOpen ? null : s.details))
  const recorded = log.data?.value ?? []
  const newest = recorded.at(-1) ?? null
  const count = `${recorded.length} ${recorded.length === 1 ? 'entry' : 'entries'}`
  return (
    <div
      role="toolbar"
      aria-label="Build line"
      data-clear="bottom"
      className="col-span-2 col-start-1 row-start-3 flex min-w-0 items-center gap-1 rounded-xl border bg-chrome/95 p-1 shadow-lg"
    >
      {newest === null ? (
        <p className="min-w-0 flex-1 px-2 text-xs text-muted-foreground">No entry yet.</p>
      ) : (
        <button
          type="button"
          className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-md px-2 py-1 text-left transition-colors duration-150 hover:bg-foreground/8"
          onClick={() => {
            openInspector()
            go(paths.system(systemId))
          }}
        >
          <span className="line-clamp-2 text-xs font-medium [overflow-wrap:anywhere]" title={newest.message}>
            <Message text={newest.message} />
          </span>
          <span className="min-w-0 truncate text-xs text-muted-foreground">
            {`${actorOf(newest)} · ${formatAgo(newest.timestamp)} · ${count}`}
          </span>
        </button>
      )}
      {held === null ? null : (
        <button
          type="button"
          title={held.title}
          className="flex min-w-0 max-w-48 shrink items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors duration-150 hover:bg-foreground/8"
          onClick={openInspector}
        >
          <PanelRightOpen className="size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 truncate">{held.title}</span>
        </button>
      )}
      <IconButton label="New request" side="top" onClick={() => useRequestDialog.getState().open({ systemId })}>
        <Plus />
      </IconButton>
      <IconButton label="Canvas tools" side="top" pressed={toolsOpen} onClick={onTools}>
        <SlidersHorizontal />
      </IconButton>
      {live ? <CalculateButton systemId={systemId} /> : null}
    </div>
  )
}
