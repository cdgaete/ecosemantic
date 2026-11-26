import { X } from 'lucide-react'
import { useUi, type EditorKind } from '@/store/ui'
import { DetailLink } from './DetailLink'
import { Icon, type IconName } from './Icon'
import { IconButton } from './IconButton'

const ICON_OF: Record<EditorKind, IconName> = { system: 'system', process: 'process', results: 'result', simulation: 'simulation', explorer: 'database' }

export function PinChips() {
  const pinned = useUi((s) => s.pinned)
  const active = useUi((s) => s.details?.id ?? null)
  const unpin = useUi((s) => s.unpin)
  if (pinned.length === 0) return null
  return (
    <div aria-label="Pinned" className="flex min-w-0 flex-wrap items-center gap-1">
      {pinned.map((tab) => (
        <span key={tab.id} className="flex min-w-0 items-center gap-1 rounded-full border bg-background pr-0.5 pl-2 text-xs">
          <DetailLink to={tab.path} aria-current={tab.id === active ? 'page' : undefined} className="flex min-w-0 items-center gap-1.5 hover:underline">
            <Icon name={ICON_OF[tab.kind]} />
            <span className="truncate" title={tab.title}>
              {tab.title}
            </span>
          </DetailLink>
          <IconButton label={`Unpin ${tab.title}`} className="size-6" onClick={() => unpin(tab.id)}>
            <X className="size-3" />
          </IconButton>
        </span>
      ))}
    </div>
  )
}
