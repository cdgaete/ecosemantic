import { screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { StatisticsPage } from '@/editors/system/StatisticsPage'
import type { SystemView } from '@/editors/system/SystemEditor'
import type { Answer, ProductSystem, ValidationReport } from '@/api/types'
import system from './fixtures/system.json'

const validationWithError: Answer<ValidationReport> = {
  hint: 'validate against a target to check one process',
  view_url: null,
  value: {
    is_valid: false,
    target: 'widget',
    roots: ['widget'],
    cases: [],
    errors: [{ case: 'no_dangling_references', code: 'dangling_reference', message: 'a link points at a process that is gone', process_codes: ['frame', 'widget'], suggestion: 'remove or relink the exchange' }],
  },
}

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, validation: vi.fn(async () => validationWithError) } }
})

describe('statistics page', () => {
  it('names the processes an error names, beside its message and suggestion', async () => {
    const view: SystemView = { id: system.value.id, system: system.value as ProductSystem, openRequests: 0, version: null }
    renderAt('/', <StatisticsPage view={view} />)
    await waitFor(() => expect(screen.getByText('dangling_reference')).toBeInTheDocument())
    expect(screen.getByText('Processes: frame, widget')).toBeInTheDocument()
    expect(screen.getByText('remove or relink the exchange')).toBeInTheDocument()
    expect(screen.getByText('validate against a target to check one process')).toBeInTheDocument()
  })

  it('names the reference process from the system, and says so when there is none', async () => {
    const doc = system.value as ProductSystem
    const widget = doc.processes.find((p) => p.code === 'widget')!
    const named: SystemView = { id: doc.id, system: { ...doc, reference_process: 'widget' }, openRequests: 0, version: null }
    const view = renderAt('/', <StatisticsPage view={named} />)
    await waitFor(() => expect(screen.getByRole('link', { name: widget.name })).toBeInTheDocument())
    view.unmount()
    renderAt('/', <StatisticsPage view={{ ...named, system: { ...doc, reference_process: null } }} />)
    await waitFor(() => expect(screen.getByText('Not set')).toBeInTheDocument())
  })
})
