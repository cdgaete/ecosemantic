import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

const COLUMN = 'min-w-0 @3xl:min-h-0 @3xl:overflow-y-auto'

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
        'grid min-h-0 flex-1 grid-cols-1 overflow-x-hidden overflow-y-auto @3xl:auto-rows-fr @3xl:overflow-hidden @3xl:grid-cols-[240px_minmax(0,1fr)]',
        detail !== null && !taken && '@5xl:grid-cols-[240px_minmax(0,1fr)_minmax(0,1fr)]',
      )}
    >
      <div className={cn(COLUMN, 'border-r px-2 py-2', open ? 'hidden @3xl:block' : 'block')}>{tree}</div>
      {taken ? null : <div className={cn(COLUMN, 'px-3 py-2 @3xl:border-r', detail === null ? 'block' : 'hidden @5xl:block')}>{table}</div>}
      {detail === null ? null : <div className={cn(COLUMN, 'px-3 py-2')}>{detail}</div>}
    </div>
  )
}
