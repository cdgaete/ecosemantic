import type { Method, MonteCarloResult, MonteCarloSummary } from '@/api/types'
import { useCategory } from '@/lib/address'
import { Histogram } from '@/editors/results/figures/Histogram'
import { categoryLabel, formatAmount, formatUnit, methodById, weightingSetName } from '@/lib/format'
import { DataTable, type Column } from '@/window/DataTable'

interface Row {
  key: string
  label: string
  summary: MonteCarloSummary | null
  unit: string | null
  reason: string | null
  total: boolean
}

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : formatAmount(value)
}

const COLUMNS: Column<Row>[] = [
  { key: 'category', header: 'Impact category', render: (r) => r.label },
  { key: 'n', header: 'n', align: 'right', folds: true, render: (r) => (r.summary === null ? '–' : String(r.summary.n)) },
  { key: 'median', header: 'Median', align: 'right', render: (r) => (r.summary === null ? r.reason : formatAmount(r.summary.median)) },
  { key: 'median-low', header: 'Median 95 % low', align: 'right', folds: true, render: (r) => fmt(r.summary?.median_ci95?.[0]) },
  { key: 'median-high', header: 'Median 95 % high', align: 'right', folds: true, render: (r) => fmt(r.summary?.median_ci95?.[1]) },
  { key: 'rel_se', header: 'Median relative SE', align: 'right', folds: true, render: (r) => fmt(r.summary?.rel_se) },
  { key: 'interval', header: '2.5 – 97.5 %', align: 'right', render: (r) => (r.summary === null ? '–' : `${fmt(r.summary.percentiles[0])} – ${fmt(r.summary.percentiles[1])}`) },
  { key: 'mean', header: 'Mean', align: 'right', folds: true, render: (r) => fmt(r.summary?.mean) },
  { key: 'unit', header: 'Unit', folds: true, render: (r) => formatUnit(r.unit) },
]

export function SimulationResults({ result, methods, systemId }: { result: MonteCarloResult; methods: Method[]; systemId: string }) {
  const { chosen, choose } = useCategory(result.categories, systemId)
  const categories = result.categories.map((category) => ({ category, method: methodById(methods, category.method_id) }))
  const rows: Row[] = [
    ...categories.map(({ category, method }) => ({
      key: `category:${category.method_id}`,
      label: categoryLabel(method),
      summary: category.summary,
      unit: method.unit,
      reason: null,
      total: false,
    })),
    ...result.totals.map((total) => ({ key: `total:${total.position}`, label: weightingSetName(total), summary: total.summary, unit: total.unit, reason: total.reason, total: true })),
  ]
  const chosenMethod = chosen === undefined ? undefined : methodById(methods, chosen.method_id)
  return (
    <>
      <label className="flex items-center gap-1 pb-2 text-xs">
        Impact category
        <select id="mc-category" className="min-w-0 flex-1 rounded-sm border bg-background px-1" value={chosen?.method_id ?? ''} onChange={(e) => choose(e.target.value)}>
          {categories.map(({ category, method }) => (
            <option key={category.method_id} value={category.method_id}>
              {categoryLabel(method)}
            </option>
          ))}
        </select>
      </label>
      {chosen !== undefined && chosenMethod !== undefined && chosen.samples !== null ? <Histogram samples={chosen.samples} mean={chosen.summary.mean} median={chosen.summary.median} percentiles={chosen.summary.percentiles} medianCi95={chosen.summary.median_ci95} unit={chosenMethod.unit} /> : null}
      <div className="pt-3">
        <DataTable columns={COLUMNS} rows={rows} rowKey={(r) => r.key} rowClassName={(r) => (r.total ? 'font-medium' : '')} unfoldAt="3xl" />
        {result.totals.length > 0 ? <p className="pt-1 text-xs text-muted-foreground">{result.totals[0].value_choices}</p> : null}
      </div>
    </>
  )
}
