import type { ReactNode } from 'react'

export function FieldGrid({ rows }: { rows: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid max-w-4xl grid-cols-1 items-baseline gap-x-4 gap-y-1 @lg:grid-cols-[160px_minmax(0,1fr)] @lg:gap-y-2">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd className="mb-1.5 break-words @lg:mb-0">{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}
