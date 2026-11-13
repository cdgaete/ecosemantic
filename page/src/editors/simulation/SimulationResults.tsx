import type { Method, MonteCarloCategory, MonteCarloResult } from '@/api/types'
import { useCategory } from '@/lib/address'
import { Histogram } from '@/editors/results/figures/Histogram'
import { categoryLabel, formatAmount, methodById } from '@/lib/format'
import { DataTable, type Column } from '@/window/DataTable'

interface CategoryRow {
  category: MonteCarloCategory
  method: Method
}

function fmt(value: number | null): string {
  return value === null ? '–' : formatAmount(value)
}

const COLUMNS: Column<CategoryRow>[] = [
  { key: 'category', header: 'Impact category', render: (r) => categoryLabel(r.method) },
  { key: 'n', header: 'n', align: 'right', render: (r) => String(r.category.summary.n) },
  { key: 'median', header: 'Median', align: 'right', render: (r) => formatAmount(r.category.summary.median) },
  { key: 'median-low', header: 'Median 95 % low', align: 'right', render: (r) => fmt(r.category.summary.median_ci95?.[0] ?? null) },
  { key: 'median-high', header: 'Median 95 % high', align: 'right', render: (r) => fmt(r.category.summary.median_ci95?.[1] ?? null) },
  { key: 'rel_se', header: 'Median relative SE', align: 'right', render: (r) => fmt(r.category.summary.rel_se) },
  { key: 'p-low', header: '2.5th pct', align: 'right', render: (r) => fmt(r.category.summary.percentiles[0]) },
  { key: 'p-high', header: '97.5th pct', align: 'right', render: (r) => fmt(r.category.summary.percentiles[1]) },
  { key: 'mean', header: 'Mean', align: 'right', render: (r) => formatAmount(r.category.summary.mean) },
  { key: 'unit', header: 'Unit', render: (r) => r.method.unit },
]

export function SimulationResults({ result, methods }: { result: MonteCarloResult; methods: Method[] }) {
  const { chosen, choose } = useCategory(result.categories)
  const rows = result.categories.map((category) => ({ category, method: methodById(methods, category.method_id) }))
  const chosenMethod = chosen === undefined ? undefined : methodById(methods, chosen.method_id)
  return (
    <>
      <label className="flex items-center gap-1 pb-2 text-xs">
        Impact category
        <select id="mc-category" className="min-w-0 flex-1 rounded-sm border bg-background px-1" value={chosen?.method_id ?? ''} onChange={(e) => choose(e.target.value)}>
          {rows.map(({ category, method }) => (
            <option key={category.method_id} value={category.method_id}>
              {categoryLabel(method)}
            </option>
          ))}
        </select>
      </label>
      {chosen !== undefined && chosenMethod !== undefined && chosen.samples !== null ? <Histogram samples={chosen.samples} mean={chosen.summary.mean} median={chosen.summary.median} percentiles={chosen.summary.percentiles} medianCi95={chosen.summary.median_ci95} unit={chosenMethod.unit} /> : null}
      <div className="pt-3">
        <DataTable columns={COLUMNS} rows={rows} rowKey={(r) => r.category.method_id} />
      </div>
    </>
  )
}
