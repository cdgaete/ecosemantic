import type { LogEntry } from '@/api/types'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { ValidationBadge } from '@/window/Badges'
import { digestOf, type DigestFilter } from './digest'

interface DigestProps {
  systemId: string
  since: number
  latest: number
  fresh: LogEntry[]
  failed: number
  filter: DigestFilter | null
  onFilter: (filter: DigestFilter | null) => void
}

function said(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

export function Digest({ systemId, since, latest, fresh, failed, filter, onFilter }: DigestProps) {
  const markSeen = useUi((s) => s.markSeen)
  if (fresh.length === 0) return <p className="px-4 pt-2 text-xs text-muted-foreground">Nothing new since #{since}.</p>
  const digest = digestOf(fresh)
  const items: [DigestFilter, string][] = [
    ['processes', said(digest.processes, 'process added', 'processes added')],
    ['exchanges', said(digest.exchanges, 'exchange added', 'exchanges added')],
    ['edits', said(digest.edits, 'value edited', 'values edited')],
    ['deletions', said(digest.deletions, 'deletion', 'deletions')],
    ['failed', said(failed, 'failed call', 'failed calls')],
  ]
  return (
    <div aria-label="Since the entry last seen" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2 text-xs">
      <span className="font-medium">Since #{since}</span>
      {items.map(([key, label]) => (
        <button key={key} type="button" aria-pressed={filter === key} className={cn('hover:underline', filter === key && 'font-semibold underline', key === 'failed' && failed > 0 && 'text-destructive')} onClick={() => onFilter(filter === key ? null : key)}>
          {label}
        </button>
      ))}
      <ValidationBadge id={systemId} />
      <button type="button" className="ml-auto text-accent hover:underline" onClick={() => markSeen(systemId, latest)}>
        Mark as seen
      </button>
    </div>
  )
}
