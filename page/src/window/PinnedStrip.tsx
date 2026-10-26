import { X } from 'lucide-react'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi, type EditorKind } from '@/store/ui'
import { Icon, type IconName } from './Icon'

const ICON_OF: Record<EditorKind, IconName> = { system: 'system', process: 'process', background: 'process', search: 'database', results: 'result', simulation: 'simulation' }

export function PinnedStrip() {
  const pinned = useUi((s) => s.pinned)
  const active = useUi((s) => s.details?.id ?? null)
  const unpin = useUi((s) => s.unpin)
  if (pinned.length === 0) return null
  return (
    <div className="flex overflow-x-auto border-b bg-chrome" role="tablist">
      {pinned.map((tab) => (
        <div
          key={tab.id}
          role="tab"
          aria-selected={tab.id === active}
          className={cn('flex items-center gap-1.5 border-r px-2.5 py-1 text-xs', tab.id === active ? '-mb-px border-b-2 border-b-primary bg-background' : 'text-muted-foreground')}
        >
          <AppLink to={tab.path} className="flex max-w-48 items-center gap-1.5">
            <Icon name={ICON_OF[tab.kind]} />
            <span className="truncate" title={tab.title}>
              {tab.title}
            </span>
          </AppLink>
          <button type="button" aria-label={`Unpin ${tab.title}`} className="opacity-60 hover:opacity-100" onClick={() => unpin(tab.id)}>
            <X className="size-3" />
          </button>
        </div>
      ))}
    </div>
  )
}
