import { screen, waitFor, within } from '@testing-library/react'
import { api } from '@/api/client'
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
const view: SystemView = { id: doc.id, system: doc, openRequests: 0, version: null, state: null }

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
          { name: 'mass', value: 1, formula: null, unit: 'kg', description: '', uncertainty: null },
          { name: 'rate', value: 0.1, formula: null, unit: '', description: '', uncertainty: null },
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

  it('names the supplier a scenario swaps in as the scenario records it', async () => {
    served.value = parameters
    served.validation = validation
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const frame = widget.exchanges.find((e) => e.name === 'frame')!
    const swapped: ProductSystem = {
      ...doc,
      scenarios: [
        {
          name: 'light',
          description: '',
          base_hash: null,
          overrides: [
            {
              kind: 'exchange',
              exchange_id: frame.id,
              amount: null,
              multiplier: null,
              input: { kind: 'foreground', code: 'frame_light' },
              name: 'light frame',
            },
          ],
        },
      ],
    }
    renderAt('/', <ParametersPage view={{ ...view, system: swapped }} />)
    const section = (await screen.findByText('Scenarios')).closest('section')!
    expect(within(section).getByText('frame on widget assembly: input light frame')).toBeInTheDocument()
    expect(within(section).queryByText(/frame_light/)).toBeNull()
  })

  it('marks nothing while every scenario is current', async () => {
    served.value = parameters
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Scenarios')).closest('section')!
    await waitFor(() => expect(within(section).getByText('electricity on widget assembly: × 0.5')).toBeInTheDocument())
    expect(within(section).queryByText('behind the base: rebase_scenario')).toBeNull()
  })

  it('holds a right-aligned value on one line rather than break a number in two', async () => {
    served.value = parameters
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Input parameters')).closest('section')!
    const row = (await within(section).findByText('frame_mass')).closest('tr')!
    const cell = row.querySelector('td[data-label="Value"]')!
    expect(cell).toHaveClass('whitespace-nowrap', 'tabular-nums')
    expect(cell.className).not.toContain('break-words')
  })

  it('folds the description the panel cannot hold under the parameter, and keeps the value in its column', async () => {
    served.value = parameters
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    for (const title of ['Input parameters', 'Dependent parameters']) {
      const section = (await screen.findByText(title)).closest('section')!
      const table = within(section).getByRole('table')
      expect(within(table).getByRole('columnheader', { name: 'Description' })).toHaveClass('hidden', '@lg:table-cell')
      expect(within(table).getByRole('columnheader', { name: 'Name' })).not.toHaveClass('hidden')
      expect(within(table).getByRole('columnheader', { name: 'Value' })).not.toHaveClass('hidden')
    }
    const input = (await screen.findByText('Input parameters')).closest('section')!
    const row = (await within(input).findByText('frame_mass')).closest('tr')!
    const folded = [...row.querySelectorAll('td')[0].children].filter((el) => el.className.includes('@lg:hidden'))
    expect(folded.map((el) => el.textContent?.trim())).toEqual(['Description: frame per widget'])
  })

  it('reads a literal parameter’s distribution beside its value', async () => {
    const answer: Answer<ParameterSpace> = {
      value: {
        parameters: [
          {
            name: 'transport_km',
            value: 175,
            formula: null,
            unit: 'km',
            description: '',
            uncertainty: { type: 'uniform', params: { minimum: 50, maximum: 300 } },
          },
          { name: 'mass', value: 1, formula: null, unit: 'kg', description: '', uncertainty: null },
        ],
        values: { transport_km: 175, mass: 1 },
        cases: [],
        matrix: { cases: [], rows: [] },
      },
      hint: null,
      view_url: null,
    }
    served.value = answer
    served.validation = validation
    renderAt('/', <ParametersPage view={view} />)
    const section = (await screen.findByText('Input parameters')).closest('section')!
    const spread = (await within(section).findByText('transport_km')).closest('tr')!
    expect(within(spread).getByText('uniform, 50 to 300 km')).toBeInTheDocument()
    expect(within(spread).getByText('175')).toBeInTheDocument()
    const plain = (await within(section).findByText('mass')).closest('tr')!
    expect(within(plain).getByText('none')).toBeInTheDocument()
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

  it('names the state it reads the parameters under and asks them with it', async () => {
    served.value = parameters
    served.validation = validation
    renderAt('/', <ParametersPage view={{ ...view, state: { kind: 'case', name: 'heavy' } }} />)
    expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
    expect(vi.mocked(api.parameters).mock.calls.at(-1)?.[2]).toBe('heavy')
  })
})
