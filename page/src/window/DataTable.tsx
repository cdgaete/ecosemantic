import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface Column<T> {
  key: string
  header: string
  align?: 'left' | 'right'
  render: (row: T) => ReactNode
}

function useStacked() {
  const box = useRef<HTMLDivElement>(null)
  const [natural, setNatural] = useState<number | null>(null)
  useLayoutEffect(() => {
    const room = box.current
    const table = room?.firstElementChild
    if (!room || !table) return
    const measure = () =>
      setNatural((stacked) => {
        if (stacked !== null) return room.clientWidth >= stacked ? null : stacked
        return table.scrollWidth > room.clientWidth ? table.scrollWidth : null
      })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(room)
    observer.observe(table)
    return () => observer.disconnect()
  }, [])
  return { box, stacked: natural !== null }
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  rowClassName,
  empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  rowClassName?: (row: T) => string
  empty?: ReactNode
}) {
  const { box, stacked } = useStacked()
  return (
    <div ref={box} className="overflow-x-auto">
      <table data-stacked={stacked || undefined} className={cn('w-full border-collapse border text-[12.5px]', stacked && 'block')}>
        <thead className={cn(stacked && 'hidden')}>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={cn('border-r border-b bg-chrome px-2 py-1 text-left font-normal whitespace-nowrap', c.align === 'right' && 'text-right')}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={cn(stacked && 'block')}>
          {rows.length === 0 && empty ? (
            <tr>
              <td className="px-2 py-2 text-muted-foreground" colSpan={columns.length}>
                {empty}
              </td>
            </tr>
          ) : null}
          {rows.map((row) => (
            <tr key={rowKey(row)} className={cn(stacked && 'block border-b py-1', rowClassName?.(row))}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  data-label={c.header}
                  className={cn(
                    'border-r border-b px-2 py-0.5 break-words [&_code]:[overflow-wrap:anywhere]',
                    c.align === 'right' && 'text-right tabular-nums',
                    stacked && 'flex min-w-0 gap-2 border-0 text-left before:w-24 before:shrink-0 before:text-muted-foreground before:content-[attr(data-label)]',
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
