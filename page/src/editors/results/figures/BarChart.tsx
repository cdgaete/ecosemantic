import { formatAmount, formatShare } from '@/lib/format'

export function BarChart({ rows, unit }: { rows: { label: string; value: number; share: number }[]; unit: string }) {
  const top = Math.max(...rows.map((r) => Math.abs(r.value)), Number.MIN_VALUE)
  return (
    <div className="grid max-w-3xl grid-cols-[minmax(140px,1fr)_3fr_auto_auto] items-center gap-x-2 gap-y-1 text-xs">
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <span className="truncate" title={r.label}>
            {r.label}
          </span>
          <svg role="img" aria-label={`${r.label}: ${formatAmount(r.value)} ${unit}`} viewBox="0 0 100 10" preserveAspectRatio="none" className="h-3 w-full">
            <rect x="0" y="0" width={(100 * Math.abs(r.value)) / top} height="10" className="fill-primary" />
          </svg>
          <span className="tabular-nums">
            {formatAmount(r.value)} {unit}
          </span>
          <span className="tabular-nums text-muted-foreground">{formatShare(r.share)}</span>
        </div>
      ))}
    </div>
  )
}
