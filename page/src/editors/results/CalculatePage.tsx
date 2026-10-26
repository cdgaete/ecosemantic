import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { keys, useCalculations, useSearchMethods, useStartRun, useSystem, useVocabulary } from '@/api/queries'
import type { Scope } from '@/api/types'
import { Button } from '@/components/ui/button'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { useUi } from '@/store/ui'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Section } from '@/window/Section'
import { useEditorTab } from '@/window/useEditorTab'
import { demandOf, serializeParams } from './params'
import { paramsOfCall } from './recorded'

function holder(error: Error): { systemId: string; runId: string } | null {
  if (!(error instanceof ApiError)) return null
  const { run_id, product_system_id } = error.details
  return typeof run_id === 'string' && typeof product_system_id === 'string' ? { systemId: product_system_id, runId: run_id } : null
}

export function CalculatePage() {
  const { id = '' } = useParams()
  const location = useLocation()
  const go = useGo()
  const read = useSystem(id)
  const system = read.data?.value
  const database = system?.database.name ?? ''
  const families = useVocabulary(database, 'impact_methods')
  const [mode, setMode] = useState<'family' | 'category'>('family')
  const calculations = useCalculations(id)
  const lastFamily = (calculations.data?.value ?? []).map((call) => paramsOfCall(call).impact_method).find((named) => named !== undefined) ?? ''
  const [chosenFamily, setFamily] = useState<string | null>(null)
  const family = chosenFamily ?? lastFamily
  const [query, setQuery] = useState('')
  const [methodId, setMethodId] = useState('')
  const hits = useSearchMethods(database, { query, limit: 15 })
  const [variants, setVariants] = useState<string[]>([])
  const [amount, setAmount] = useState(1)
  const [kind, setKind] = useState<'result' | 'simulation'>(() => (new URLSearchParams(location.search).get('kind') === 'simulation' ? 'simulation' : 'result'))
  const [scope, setScope] = useState<Scope>('full')
  const start = useStartRun(id)
  const client = useQueryClient()
  const [mcParams, setMcParams] = useState({ n_min: 30, n_max: 200, rel_se_target: 0.05, seed: 12345 })
  useEditorTab({ id: `calculate:${id}`, kind: 'results', title: `Calculation of: ${system?.name ?? ''}`, path: paths.results(id, 'setup', '') })
  if (!system) return <p className="p-4 text-muted-foreground">{read.error?.message ?? 'Loading…'}</p>
  const names = [...system.scenarios.map((s) => s.name), ...system.cases.map((c) => c.name)]
  const ready = mode === 'family' ? family !== '' : methodId !== ''
  const rootCode = system.reference_process
  const run = () => {
    const method = mode === 'family' ? { impact_method: family } : { method_id: methodId }
    if (kind === 'simulation') {
      const demand = demandOf({ variants: [], amount }, rootCode)
      start.mutate({ ...method, ...(demand ? { demand } : {}), monte_carlo: { ...mcParams, scope } }, { onSuccess: (answer) => go(paths.simulation(id, answer.value.id)) })
      return
    }
    useUi.getState().startImpact(id)
    client.removeQueries({ queryKey: keys.impacts(id) })
    go(paths.results(id, 'impact', serializeParams({ ...method, variants, amount })))
  }
  const root = system.processes.find((p) => p.code === rootCode)
  return (
    <>
      <EditorHeader icon="result" page="Calculation" entity={system.name} />
      <Section title="Calculation" sectionKey={`results:${id}:setup`}>
        <FieldGrid
          rows={[
            {
              label: 'Calculation type',
              value: (
                <span className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1">
                    <input type="radio" name="kind" checked={kind === 'result'} onChange={() => setKind('result')} /> Impact result
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="radio" name="kind" checked={kind === 'simulation'} onChange={() => setKind('simulation')} /> Monte Carlo simulation
                  </label>
                </span>
              ),
            },
            {
              label: 'Impact assessment',
              value: (
                <span className="flex min-w-0 flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1">
                    <input type="radio" name="mode" checked={mode === 'family'} onChange={() => setMode('family')} /> Method
                  </label>
                  <label htmlFor="calc-family" className="flex min-w-0 max-w-full items-center gap-1">
                    Family
                    <select id="calc-family" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={family} disabled={mode !== 'family'} onChange={(e) => setFamily(e.target.value)}>
                      <option value="">choose…</option>
                      {(families.data?.value ?? []).map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.value}
                          {t.detail ? ` (${t.detail})` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="radio" name="mode" checked={mode === 'category'} onChange={() => setMode('category')} /> One category
                  </label>
                  <label htmlFor="calc-query" className="flex items-center gap-1">
                    Search
                    <input id="calc-query" className="rounded-sm border bg-background px-1" placeholder="search…" value={query} disabled={mode !== 'category'} onChange={(e) => setQuery(e.target.value)} />
                  </label>
                  <label htmlFor="calc-method" className="flex min-w-0 max-w-full items-center gap-1">
                    Category
                    <select id="calc-method" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={methodId} disabled={mode !== 'category'} onChange={(e) => setMethodId(e.target.value)}>
                      <option value="">choose…</option>
                      {(hits.data?.items ?? []).map((m) => (
                        <option key={m.id} value={m.id}>
                          {[m.impact_method, m.impact_category, m.indicator].filter(Boolean).join(' › ')} [{m.unit}]
                        </option>
                      ))}
                    </select>
                  </label>
                </span>
              ),
            },
            ...(kind === 'result'
              ? [
                  {
                    label: 'Variants',
                    value:
                      names.length === 0 ? (
                        <span className="text-muted-foreground">No scenario or case.</span>
                      ) : (
                        <span className="flex flex-wrap gap-3">
                          {names.map((name) => (
                            <label key={name} className="flex items-center gap-1">
                              <input type="checkbox" checked={variants.includes(name)} onChange={(e) => setVariants(e.target.checked ? [...variants, name] : variants.filter((v) => v !== name))} /> {name}
                            </label>
                          ))}
                        </span>
                      ),
                  },
                ]
              : []),
            {
              label: 'Target amount',
              value: (
                <span className="flex items-center gap-2">
                  <label htmlFor="calc-amount" className="flex items-center gap-1">
                    Amount
                    <input id="calc-amount" type="number" step="any" className="w-24 rounded-sm border bg-background px-1 text-right" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
                  </label>
                  {root ? `${root.unit} of ${root.reference_product}` : 'no reference process is set; see Statistics'}
                </span>
              ),
            },
            ...(kind === 'simulation'
              ? [
                  {
                    label: 'Monte Carlo',
                    value: (
                      <span className="flex flex-wrap items-center gap-3">
                        {(['n_min', 'n_max', 'rel_se_target', 'seed'] as const).map((k) => (
                          <label key={k} className="flex items-center gap-1">
                            {k}
                            <input type="number" step="any" className="w-20 rounded-sm border bg-background px-1 text-right" value={mcParams[k]} onChange={(e) => setMcParams({ ...mcParams, [k]: Number(e.target.value) })} />
                          </label>
                        ))}
                        <label htmlFor="calc-scope" className="flex items-center gap-1">
                          Uncertainty in
                          <select id="calc-scope" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
                            <option value="full">all exchanges</option>
                            <option value="biosphere_only">elementary flows only</option>
                          </select>
                        </label>
                      </span>
                    ),
                  },
                ]
              : []),
          ]}
        />
        <div className="pt-3">
          <Button size="sm" disabled={!ready || start.isPending} onClick={run}>
            Calculate
          </Button>
        </div>
        {start.error ? (
          <p className="pt-2 text-destructive">
            <span>{start.error.message}</span>
            {(() => {
              const open = holder(start.error)
              return open ? (
                <>
                  {' '}
                  <AppLink to={paths.simulation(open.systemId, open.runId)} className="underline">
                    Open that simulation
                  </AppLink>
                </>
              ) : null
            })()}
          </p>
        ) : null}
      </Section>
    </>
  )
}
