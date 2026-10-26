import type { MonteCarloCategory, MonteCarloResult } from '@/api/types'
import { useCategory } from '@/lib/address'
import { Histogram } from '@/editors/results/figures/Histogram'
import { categoryLabel, formatAmount } from '@/lib/format'
import { DataTable, type Column } from '@/window/DataTable'

function fmt(value: number | null): string {
  return value === null ? '–' : formatAmount(value)
}

const COLUMNS: Column<MonteCarloCategory>[] = [
  { key: 'category', header: 'Impact category', render: (c) => categoryLabel(c.method) },
  { key: 'n', header: 'n', align: 'right', render: (c) => String(c.summary.n) },
  { key: 'median', header: 'Median', align: 'right', render: (c) => formatAmount(c.summary.median) },
  { key: 'median-low', header: 'Median 95 % low', align: 'right', render: (c) => fmt(c.summary.median_ci95?.[0] ?? null) },
  { key: 'median-high', header: 'Median 95 % high', align: 'right', render: (c) => fmt(c.summary.median_ci95?.[1] ?? null) },
  { key: 'rel_se', header: 'Median relative SE', align: 'right', render: (c) => fmt(c.summary.rel_se) },
  { key: 'p-low', header: '2.5th pct', align: 'right', render: (c) => fmt(c.summary.percentiles[0]) },
  { key: 'p-high', header: '97.5th pct', align: 'right', render: (c) => fmt(c.summary.percentiles[1]) },
  { key: 'mean', header: 'Mean', align: 'right', render: (c) => formatAmount(c.summary.mean) },
  { key: 'unit', header: 'Unit', render: (c) => c.method.unit },
]

export function SimulationResults({ result }: { result: MonteCarloResult }) {
  const { chosen, choose } = useCategory(result.categories)
  return (
    <>
      <label className="flex items-center gap-1 pb-2 text-xs">
        Impact category
        <select id="mc-category" className="min-w-0 flex-1 rounded-sm border bg-background px-1" value={chosen?.method.id ?? ''} onChange={(e) => choose(e.target.value)}>
          {result.categories.map((c) => (
            <option key={c.method.id} value={c.method.id}>
              {categoryLabel(c.method)}
            </option>
          ))}
        </select>
      </label>
      {chosen ? <Histogram samples={chosen.samples} mean={chosen.summary.mean} median={chosen.summary.median} percentiles={chosen.summary.percentiles} medianCi95={chosen.summary.median_ci95} unit={chosen.method.unit} /> : null}
      <div className="pt-3">
        <DataTable columns={COLUMNS} rows={result.categories} rowKey={(c) => c.method.id} />
      </div>
    </>
  )
}
