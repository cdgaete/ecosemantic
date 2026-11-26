import type { ReactNode } from 'react'

interface FieldRow {
  label: string
  value: ReactNode
  empty?: string
}

function absent(value: ReactNode): boolean {
  return value === null || value === undefined || (typeof value === 'string' && value.trim() === '')
}

function shown(value: ReactNode): ReactNode {
  return typeof value === 'boolean' ? String(value) : value
}

export const PENDING = <span className="text-muted-foreground">Loading…</span>

export function FieldGrid({ rows, empty }: { rows: FieldRow[]; empty?: string }) {
  if (empty !== undefined && rows.every((row) => absent(row.value))) return <p className="text-muted-foreground">{empty}</p>
  return (
    <dl className="grid max-w-4xl grid-cols-1 items-baseline gap-x-4 gap-y-1 @lg:grid-cols-[160px_minmax(0,1fr)] @lg:gap-y-2">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd className="mb-1.5 break-words @lg:mb-0">
            {absent(row.value) ? <span className="text-muted-foreground">{row.empty ?? 'Not provided'}</span> : shown(row.value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}
