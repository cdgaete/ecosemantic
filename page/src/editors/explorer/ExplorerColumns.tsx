import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function ExplorerColumns({
  tree,
  table,
  detail,
  open,
  wide,
}: {
  tree: ReactNode
  table: ReactNode
  detail: ReactNode | null
  open: boolean
  wide: boolean
}) {
  const taken = wide && detail !== null
  return (
    <div
      className={cn(
        'grid min-h-0 flex-1 grid-cols-1 @3xl:grid-cols-[240px_minmax(0,1fr)]',
        detail !== null && !taken && '@5xl:grid-cols-[240px_minmax(0,1fr)_minmax(0,1fr)]',
      )}
    >
      <div className={cn('min-w-0 border-r px-2 py-2', open ? 'hidden @3xl:block' : 'block')}>{tree}</div>
      {taken ? null : <div className={cn('min-w-0 px-3 py-2 @3xl:border-r', detail === null ? 'block' : 'hidden @5xl:block')}>{table}</div>}
      {detail === null ? null : <div className="min-w-0 px-3 py-2">{detail}</div>}
    </div>
  )
}
