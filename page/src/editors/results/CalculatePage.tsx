import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { useCalculations, useMethodTree, useMonteCarloDefaults, useStartRun, useSystem, useVocabulary } from '@/api/queries'
import type { Method, MethodFamily, MonteCarloConfig, Scope } from '@/api/types'
import { Button } from '@/components/ui/button'
import { categoryLabel } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { EditorHeader } from '@/window/EditorHeader'
import { FieldGrid } from '@/window/FieldGrid'
import { Section } from '@/window/Section'
import { useCanvasVariant } from '@/window/useCanvasState'
import { useEditorTab } from '@/window/useEditorTab'
import { demandOf, serializeParams } from './params'
import { paramsOfCall } from './recorded'
import { useStartImpact } from './useStartImpact'

function holder(error: Error): { systemId: string; runId: string } | null {
  if (!(error instanceof ApiError)) return null
  const { run_id, product_system_id } = error.details
  return typeof run_id === 'string' && typeof product_system_id === 'string' ? { systemId: product_system_id, runId: run_id } : null
}

const DRAWS: { key: 'n_min' | 'n_max' | 'rel_se_target' | 'seed'; label: string }[] = [
  { key: 'n_min', label: 'Fewest draws' },
  { key: 'n_max', label: 'Most draws' },
  { key: 'rel_se_target', label: 'Target precision' },
  { key: 'seed', label: 'Seed' },
]

function categoriesOf(families: MethodFamily[], named: string): Method[] {
  return families.find((family) => family.name === named)?.categories.flatMap((category) => category.indicators) ?? []
}

function familyOf(families: MethodFamily[], methodId: string): string {
  return families.find((family) => categoriesOf(families, family.name).some((method) => method.id === methodId))?.name ?? ''
}

export function CalculatePage() {
  const { id = '' } = useParams()
  const location = useLocation()
  const go = useGo()
  const read = useSystem(id)
  const system = read.data?.value
  const database = system?.database.name ?? ''
  const listed = useVocabulary(database, 'impact_methods')
  const tree = useMethodTree(database)
  const calculations = useCalculations(id)
  const families = tree.data?.value ?? []
  const last = (calculations.data?.value ?? []).map(paramsOfCall).find((named) => named.impact_method !== undefined || named.method_id !== undefined)
  const lastFamily = last?.impact_method ?? (last?.method_id === undefined ? '' : familyOf(families, last.method_id))
  const [chosenFamily, setFamily] = useState<string | null>(null)
  const family = chosenFamily ?? lastFamily
  const [chosenMethod, setMethodId] = useState<string | null>(null)
  const offered = categoriesOf(families, family)
  const lastMethod = last?.method_id ?? ''
  const methodId = chosenMethod ?? (offered.some((method) => method.id === lastMethod) ? lastMethod : '')
  const [chosen, setChosen] = useState<string[] | null>(null)
  const [amount, setAmount] = useState(1)
  const [kind, setKind] = useState<'result' | 'simulation'>(() => (new URLSearchParams(location.search).get('kind') === 'simulation' ? 'simulation' : 'result'))
  const state = useCanvasVariant(system)
  const start = useStartRun(id)
  const startImpact = useStartImpact(id)
  const defaults = useMonteCarloDefaults()
  const [mcParams, setMcParams] = useState<Omit<MonteCarloConfig, 'n'> | null>(null)
  useEffect(() => {
    const answered = defaults.data?.value
    if (answered === undefined) return
    setMcParams({ n_min: answered.n_min, n_max: answered.n_max, rel_se_target: answered.rel_se_target, seed: answered.seed, scope: answered.scope })
  }, [defaults.data])
  useEditorTab({ id: `calculate:${id}`, kind: 'results', title: `Calculation of: ${system?.name ?? ''}`, path: paths.results(id, 'setup', '') })
  if (!system) return <p className="p-4 text-muted-foreground">{read.error?.message ?? 'Loading…'}</p>
  const options = [...system.scenarios.map((s) => s.name), ...system.cases.map((c) => c.name)]
  const variants = chosen ?? (state === null ? [] : [state.name])
  const ready = family !== '' && (kind === 'result' || mcParams !== null)
  const rootCode = system.reference_process
  const run = () => {
    const method = methodId === '' ? { impact_method: family } : { method_id: methodId }
    if (kind === 'simulation') {
      if (mcParams === null) return
      const demand = demandOf({ variants: [], amount }, rootCode)
      start.mutate({ ...method, ...(demand ? { demand } : {}), monte_carlo: mcParams }, { onSuccess: (answer) => go(paths.simulation(id, answer.value.id)) })
      return
    }
    startImpact('impact', serializeParams({ ...method, variants, amount }))
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
                  <label htmlFor="calc-family" className="flex min-w-0 max-w-full items-center gap-1">
                    Method
                    <select
                      id="calc-family"
                      className="min-w-0 max-w-full rounded-sm border bg-background px-1"
                      value={family}
                      onChange={(e) => {
                        setFamily(e.target.value)
                        setMethodId('')
                      }}
                    >
                      <option value="">choose…</option>
                      {(listed.data?.value ?? []).map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.value}
                          {t.detail ? ` (${t.detail})` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label htmlFor="calc-method" className="flex min-w-0 max-w-full items-center gap-1">
                    Category
                    <select id="calc-method" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={methodId} disabled={family === ''} onChange={(e) => setMethodId(e.target.value)}>
                      <option value="">All categories</option>
                      {offered.map((m) => (
                        <option key={m.id} value={m.id}>
                          {categoryLabel(m)} [{m.unit}]
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
                      options.length === 0 ? (
                        <span className="text-muted-foreground">No scenario or case.</span>
                      ) : (
                        <span className="flex flex-col gap-1">
                          {state !== null && variants.includes(state.name) ? (
                            <span>
                              The canvas shows {state.kind} {state.name}; it is ticked below.
                            </span>
                          ) : null}
                          <span className="flex flex-wrap gap-3">
                            {options.map((name) => (
                              <label key={name} className="flex items-center gap-1">
                                <input type="checkbox" checked={variants.includes(name)} onChange={(e) => setChosen(e.target.checked ? [...variants, name] : variants.filter((v) => v !== name))} /> {name}
                              </label>
                            ))}
                          </span>
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
            ...(kind === 'simulation' && mcParams !== null
              ? [
                  {
                    label: 'Monte Carlo',
                    value: (
                      <span className="flex flex-wrap items-center gap-3">
                        {DRAWS.map(({ key, label }) => (
                          <label key={key} title={key} className="flex items-center gap-1">
                            {label}
                            <input type="number" step="any" className="w-20 rounded-sm border bg-background px-1 text-right" value={mcParams[key]} onChange={(e) => setMcParams({ ...mcParams, [key]: Number(e.target.value) })} />
                          </label>
                        ))}
                        <label htmlFor="calc-scope" title="scope" className="flex items-center gap-1">
                          Uncertainty in
                          <select id="calc-scope" className="min-w-0 max-w-full rounded-sm border bg-background px-1" value={mcParams.scope} onChange={(e) => setMcParams({ ...mcParams, scope: e.target.value as Scope })}>
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
