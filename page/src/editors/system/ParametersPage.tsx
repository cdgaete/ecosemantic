import { useParameters, useValidation } from '@/api/queries'
import type { CaseRow, Override, Parameter, ProductSystem } from '@/api/types'
import { formatAmount, shortHash } from '@/lib/format'
import { RequestAction } from '@/requests/RequestAction'
import { DataTable, type Column } from '@/window/DataTable'
import { EditorHeader } from '@/window/EditorHeader'
import { Section } from '@/window/Section'
import type { SystemView } from './SystemEditor'

const inputColumns: Column<Parameter>[] = [
  { key: 'name', header: 'Name', render: (p) => p.name },
  { key: 'value', header: 'Value', align: 'right', render: (p) => (p.value === null ? '' : formatAmount(p.value)) },
  { key: 'unit', header: 'Unit', render: (p) => p.unit },
  { key: 'description', header: 'Description', render: (p) => p.description },
]

function dependentColumns(values: Record<string, number>): Column<Parameter>[] {
  return [
    { key: 'name', header: 'Name', render: (p) => p.name },
    { key: 'formula', header: 'Formula', render: (p) => <code>{p.formula}</code> },
    { key: 'value', header: 'Value', align: 'right', render: (p) => (values[p.name] === undefined ? '' : formatAmount(values[p.name])) },
    { key: 'unit', header: 'Unit', render: (p) => p.unit },
    { key: 'description', header: 'Description', render: (p) => p.description },
  ]
}

function exchangeLabel(system: ProductSystem, exchangeId: string): string {
  for (const process of system.processes) {
    const exchange = process.exchanges.find((e) => e.id === exchangeId)
    if (exchange) return `${exchange.name} on ${process.name}`
  }
  return `exchange ${exchangeId}`
}

function describeOverride(system: ProductSystem, o: Override): string {
  if (o.kind === 'parameter') return `parameter ${o.name} = ${formatAmount(o.value)}`
  const label = exchangeLabel(system, o.exchange_id)
  if (o.amount !== null) return `${label}: amount ${formatAmount(o.amount)}`
  if (o.multiplier !== null) return `${label}: × ${formatAmount(o.multiplier)}`
  const input = o.input
  return `${label}: input ${input?.kind === 'background' ? input.id : input?.kind === 'elementary_flow' ? input.id : (input?.code ?? '')}`
}

export function ParametersPage({ view }: { view: SystemView }) {
  const { id, system } = view
  const read = useParameters(id, view.version)
  const validation = useValidation(id, view.version === null)
  const scenarioCase = validation.data?.value.cases.find((c) => c.id === 'scenarios_current')
  const behind = new Set(scenarioCase && !scenarioCase.passed && scenarioCase.detail ? scenarioCase.detail.split(', ') : [])
  const key = (s: string) => `system:${id}:${s}`
  const action = (entity: 'parameter' | 'case' | 'scenario', entityId?: string) => (view.version ? undefined : <RequestAction systemId={id} entity={entity} entityId={entityId} />)
  const space = read.data?.value
  const matrix = space?.matrix ?? { cases: [], rows: [] }
  return (
    <>
      <EditorHeader icon="parameter" page="Parameters" entity={system.name} />
      {read.error ? <p className="px-4 text-destructive">{read.error.message}</p> : null}
      <Section title="Input parameters" sectionKey={key('input-parameters')} actions={action('parameter')}>
        <DataTable columns={inputColumns} rows={(space?.parameters ?? []).filter((p) => p.formula === null)} rowKey={(p) => p.name} empty="No literal parameter." />
      </Section>
      <Section title="Dependent parameters" sectionKey={key('dependent-parameters')} actions={action('parameter')}>
        <DataTable columns={dependentColumns(space?.values ?? {})} rows={(space?.parameters ?? []).filter((p) => p.formula !== null)} rowKey={(p) => p.name} empty="No formula parameter." />
      </Section>
      <Section title="Cases" sectionKey={key('cases')} actions={action('case')}>
        <DataTable
          columns={[
            { key: 'parameter', header: 'Parameter', render: (r: CaseRow) => r.parameter },
            ...matrix.cases.map((name, i) => ({ key: name, header: name, align: 'right' as const, render: (r: CaseRow) => (r.values[i] === null || r.values[i] === undefined ? '' : formatAmount(r.values[i]!)) })),
          ]}
          rows={matrix.rows}
          rowKey={(r) => r.parameter}
          empty="No case."
        />
      </Section>
      <Section title="Scenarios" sectionKey={key('scenarios')} actions={action('scenario')}>
        {system.scenarios.length === 0 ? <p className="text-muted-foreground">No scenario.</p> : null}
        {system.scenarios.map((s) => (
          <div key={s.name} className="mb-2">
            <div className="font-semibold">
              {s.name} <span className="font-normal text-muted-foreground">{s.description}</span> <span className="font-normal text-muted-foreground">base {shortHash(s.base_hash)}</span>
              {behind.has(s.name) ? <span className="ml-2 font-normal text-destructive">behind the base: rebase_scenario</span> : null}
            </div>
            <ul className="list-disc pl-5">
              {s.overrides.map((o, i) => (
                <li key={i}>{describeOverride(system, o)}</li>
              ))}
            </ul>
          </div>
        ))}
      </Section>
    </>
  )
}
