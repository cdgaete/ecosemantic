import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export const NUMERIC = 'whitespace-nowrap tabular-nums'

export type FoldWidth = 'lg' | '2xl' | '3xl'

const FOLD: Record<FoldWidth, { cell: string; line: string }> = {
  lg: { cell: 'hidden @lg:table-cell', line: '@lg:hidden' },
  '2xl': { cell: 'hidden @2xl:table-cell', line: '@2xl:hidden' },
  '3xl': { cell: 'hidden @3xl:table-cell', line: '@3xl:hidden' },
}

export interface Column<T> {
  key: string
  header: string
  align?: 'left' | 'right'
  width?: 'rest' | 'content'
  folds?: boolean
  render: (row: T) => ReactNode
}

export interface SummaryRow {
  key: string
  className?: string
  cells: Record<string, ReactNode>
}

const CELL = 'border-r border-b px-2 py-0.5'
const STACKED_CELL =
  'flex min-w-0 gap-2 border-0 text-left before:w-24 before:shrink-0 before:text-muted-foreground before:content-[attr(data-label)]'

function cellClass<T>(column: Column<T>, stacked: boolean, fold: { cell: string }): string {
  return cn(
    CELL,
    column.align === 'right' ? cn(NUMERIC, 'text-right') : 'break-words [&_code]:[overflow-wrap:anywhere]',
    !stacked && column.width === 'rest' && 'w-full',
    !stacked && column.width === 'content' && 'whitespace-nowrap',
    !stacked && column.folds && fold.cell,
    stacked && STACKED_CELL,
  )
}

function headerClass<T>(column: Column<T>, fold: { cell: string }): string {
  return cn(
    'border-r border-b bg-chrome px-2 py-1 text-left font-normal break-words',
    column.align === 'right' && 'text-right',
    column.width === 'rest' && 'w-full',
    column.folds && fold.cell,
  )
}

function Cells<T>({
  columns,
  stacked,
  fold,
  value,
}: {
  columns: Column<T>[]
  stacked: boolean
  fold: { cell: string; line: string }
  value: (column: Column<T>) => ReactNode
}) {
  const folded = columns.filter((c) => c.folds)
  return (
    <>
      {columns.map((c, i) => (
        <td key={c.key} data-label={c.header} className={cellClass(c, stacked, fold)}>
          {value(c)}
          {i === 0 && !stacked
            ? folded.map((f) => (
                <span key={f.key} className={cn('block whitespace-normal text-xs', fold.line)}>
                  <span className="text-muted-foreground">{f.header}:</span>{' '}
                  <span className={cn(f.align === 'right' && NUMERIC)}>{value(f)}</span>
                </span>
              ))
            : null}
        </td>
      ))}
    </>
  )
}

function useStacked() {
  const box = useRef<HTMLDivElement>(null)
  const [stacked, setStacked] = useState(false)
  useLayoutEffect(() => {
    const room = box.current
    const table = room?.firstElementChild
    if (!room || !table) return
    if (stacked) {
      let seen = room.clientWidth
      const observer = new ResizeObserver(() => {
        if (room.clientWidth === seen) return
        seen = room.clientWidth
        setStacked(false)
      })
      observer.observe(room)
      return () => observer.disconnect()
    }
    const measure = () => setStacked(table.scrollWidth > room.clientWidth)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(room)
    observer.observe(table)
    return () => observer.disconnect()
  }, [stacked])
  return { box, stacked }
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  rowClassName,
  empty,
  summary,
  unfoldAt = 'lg',
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  rowClassName?: (row: T) => string
  empty?: ReactNode
  summary?: SummaryRow[]
  unfoldAt?: FoldWidth
}) {
  const { box, stacked } = useStacked()
  const fold = FOLD[unfoldAt]
  return (
    <div ref={box} className="overflow-x-auto">
      <table data-stacked={stacked || undefined} className={cn('w-full border-collapse border text-[12.5px]', stacked && 'block')}>
        <thead className={cn(stacked && 'hidden')}>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={headerClass(c, fold)}>
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
              <Cells columns={columns} stacked={stacked} fold={fold} value={(c) => c.render(row)} />
            </tr>
          ))}
          {summary?.map((row) => (
            <tr key={`summary:${row.key}`} className={cn(stacked && 'block border-b py-1', row.className)}>
              <Cells columns={columns} stacked={stacked} fold={fold} value={(c) => row.cells[c.key]} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
