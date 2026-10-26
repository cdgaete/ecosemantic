import { screen, waitFor, within } from '@testing-library/react'
import { ParametersPage } from '@/editors/system/ParametersPage'
import type { SystemView } from '@/editors/system/SystemEditor'
import type { Answer, ParameterSpace, ProductSystem, ValidationReport } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { renderAt } from './render'
import parameters from './fixtures/parameters.json'
import system from './fixtures/system.json'
import validation from './fixtures/validation.json'

const served = vi.hoisted(() => ({ value: null as unknown, validation: null as unknown }))

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, parameters: vi.fn(async () => served.value), validation: vi.fn(async () => served.validation) } }
})

const doc = system.value as ProductSystem
const view: SystemView = { id: doc.id, system: doc, openRequests: 0, version: null }

async function cases(columns: string[]): Promise<HTMLElement> {
  renderAt('/', <ParametersPage view={view} />)
  const section = (await screen.findByText('Cases')).closest('section')!
  const table = within(section).getByRole('table')
  await waitFor(() =>
    expect(within(table).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Parameter',
      ...columns,
    ]),
  )
  return table
}

describe('parameters page', () => {
  it('renders the matrix the server derived, one column per case', async () => {
    served.value = parameters
    const table = await cases(['heavy'])
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['frame_mass', '0.5'])
  })

  it('leaves a cell blank where a case leaves the base value', async () => {
    const answer: Answer<ParameterSpace> = {
      value: {
        parameters: [
          { name: 'mass', value: 1, formula: null, unit: 'kg', description: '' },
          { name: 'rate', value: 0.1, formula: null, unit: '', description: '' },
        ],
        values: { mass: 1, rate: 0.1 },
        cases: [
          { name: 'small', description: '', values: { mass: 0.5 } },
          { name: 'large', description: '', values: { mass: 2, rate: 0.2 } },
        ],
        matrix: {
          cases: ['small', 'large'],
          rows: [
            { parameter: 'mass', values: [0.5, 2] },
            { parameter: 'rate', values: [null, 0.2] },
          ],
        },
      },
      hint: null,
      view_url: null,
    }
    served.value = answer
    const table = await cases(['small', 'large'])
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['mass', '0.5', '2'])
    expect(within(rows[2]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['rate', '', '0.2'])
  })

  it('names each override by the flow and process it changes and marks a scenario behind the base', async () => {
    served.value = parameters
    const report = validation as Answer<ValidationReport>
    served.validation = {
      ...report,
      value: {
        ...report.value,
        is_valid: false,
        cases: [...report.value.cases.filter((c) => c.id !== 'scenarios_current'), { id: 'scenarios_current', passed: false, detail: 'lighter' }],
      },
    }
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Scenarios')).closest('section')!
    expect(within(section).getByText('electricity on widget assembly: × 0.5')).toBeInTheDocument()
    expect(await within(section).findByText('behind the base: rebase_scenario')).toBeInTheDocument()
  })

  it('marks nothing while every scenario is current', async () => {
    served.value = parameters
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Scenarios')).closest('section')!
    await waitFor(() => expect(within(section).getByText('electricity on widget assembly: × 0.5')).toBeInTheDocument())
    expect(within(section).queryByText('behind the base: rebase_scenario')).toBeNull()
  })

  it('shows each derived parameter with the value it evaluates to', async () => {
    const answer = parameters as Answer<ParameterSpace>
    const derived = answer.value.parameters.find((p) => p.formula !== null)!
    served.value = answer
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Dependent parameters')).closest('section')!
    const row = (await within(section).findByText(derived.name)).closest('tr')!
    expect(within(row).getAllByRole('cell').map((c) => c.textContent)).toContain(formatAmount(answer.value.values[derived.name]))
  })
})
