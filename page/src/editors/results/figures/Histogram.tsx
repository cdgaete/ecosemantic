import { formatAmount } from '@/lib/format'
import { bins } from '@/lib/histogram'

export function Histogram({ samples, mean, median, percentiles, medianCi95, unit }: { samples: number[]; mean: number; median: number; percentiles: [number, number]; medianCi95: [number, number] | null; unit: string }) {
  const rows = bins(samples, 24)
  const W = 640
  const H = 220
  const pad = { l: 40, r: 12, t: 12, b: 32 }
  const low = rows[0]?.x0 ?? 0
  const high = rows.at(-1)?.x1 ?? 1
  const tall = Math.max(...rows.map((b) => b.n), 1)
  const plot = W - pad.l - pad.r
  const single = high === low
  const x = (v: number) => (single ? pad.l + plot / 2 : pad.l + ((v - low) / (high - low)) * plot)
  const y = (n: number) => H - pad.b - (n / tall) * (H - pad.t - pad.b)
  const marks: { at: number; label: string; cls: string }[] = [
    { at: mean, label: 'mean', cls: 'stroke-primary' },
    { at: median, label: 'median', cls: 'stroke-accent' },
    { at: percentiles[0], label: '2.5th pct', cls: 'stroke-warning' },
    { at: percentiles[1], label: '97.5th pct', cls: 'stroke-warning' },
  ]
  return (
    <figure>
      <svg role="img" aria-label={`Histogram of ${samples.length} samples`} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[640px]">
        <line x1={pad.l} y1={H - pad.b} x2={W - pad.r} y2={H - pad.b} className="stroke-border" />
        <line x1={pad.l} y1={pad.t} x2={pad.l} y2={H - pad.b} className="stroke-border" />
        {rows.map((b) => (
          <rect key={b.x0} x={single ? pad.l + plot / 2 - plot / 48 : x(b.x0)} y={y(b.n)} width={single ? plot / 24 : Math.max(1, x(b.x1) - x(b.x0) - 1)} height={H - pad.b - y(b.n)} className="fill-primary/70" />
        ))}
        {marks.map((m) => (
          <line key={m.label} x1={x(m.at)} y1={pad.t} x2={x(m.at)} y2={H - pad.b} className={m.cls} strokeDasharray="4 3" />
        ))}
      </svg>
      <div aria-label="Axis" className="flex w-full max-w-[640px] justify-between text-xs text-muted-foreground tabular-nums" style={{ paddingLeft: `${(pad.l / W) * 100}%`, paddingRight: `${(pad.r / W) * 100}%` }}>
        <span>{formatAmount(low)}</span>
        <span>
          {formatAmount(high)} {unit}
        </span>
      </div>
      <ul aria-label="Markers" className="flex flex-wrap gap-x-4 gap-y-1 py-1 text-xs">
        {marks.map((m) => (
          <li key={m.label} className="flex items-center gap-1.5">
            <svg aria-hidden="true" width="18" height="2" className="overflow-visible">
              <line x1="0" y1="1" x2="18" y2="1" className={m.cls} strokeWidth="2" strokeDasharray="4 3" />
            </svg>
            {m.label}
          </li>
        ))}
      </ul>
      <figcaption className="text-xs text-muted-foreground">
        {samples.length} samples, at most {tall} in a bar · mean {formatAmount(mean)} · median {formatAmount(median)} · 2.5th to 97.5th percentile {formatAmount(percentiles[0])} to{' '}
        {formatAmount(percentiles[1])} · 95 % interval of the median {medianCi95 === null ? '–' : `${formatAmount(medianCi95[0])} to ${formatAmount(medianCi95[1])}`} {unit}
      </figcaption>
    </figure>
  )
}
