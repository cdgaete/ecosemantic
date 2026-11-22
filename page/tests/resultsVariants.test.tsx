import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { firstMethodOf } from './method'
import { App } from '@/App'
import { api } from '@/api/client'
import type { ContributionArguments } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { useUi } from '@/store/ui'
import { useFiles } from '@/window/files'
import type { ResultKind } from '@/window/menus'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import validation from './fixtures/validation.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import byProcess from './fixtures/contributions_process.json'
import byPath from './fixtures/contributions_path.json'
import byFlow from './fixtures/contributions_flow.json'

const withVariant = {
  ...impact,
  value: {
    ...impact.value,
    variants: [
      {
        name: 'small',
        scores: impact.value.scores.map((s) => ({ ...s, value: s.value / 2 })),
        deltas: impact.value.scores.map((s) => -(s.value / 2)),
        credit_loops: [],
        treatments_run_backwards: [],
      },
    ],
  },
}

function answer(body: ContributionArguments) {
  if (body.by === 'path') return byPath
  if (body.by === 'flow') return byFlow
  return byProcess
}

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      validation: vi.fn(async () => validation),
      impact: vi.fn(async () => withVariant),
      contributions: vi.fn(async (_id: string, body: ContributionArguments) => answer(body)),
      inventory: vi.fn(async () => inventory),
      resultZip: vi.fn(async () => ({ blob: new Blob(['zip']), name: 'result.zip' })),
    },
  }
})

const id = system.value.id
const method = encodeURIComponent(firstMethodOf(impact.value).impact_method)
// App holds one query client for the whole file, so each address carries an amount
// of its own and no page reads an answer a test before it asked for.
const at = (page: string, amount: number) => `/systems/${id}/results/${page}?impact_method=${method}&amount=${amount}`
const underCase = (page: string) => `${at(page, 2)}&variant=heavy`
const underNoCase = (page: string) => at(page, 3)

const contributionsBodies = () => vi.mocked(api.contributions).mock.calls.map(([, body]) => body)
const inventoryBodies = () => vi.mocked(api.inventory).mock.calls.map(([, body]) => body)

function Download({ kind }: { kind: ResultKind }) {
  const files = useFiles()
  return (
    <button type="button" onClick={() => files.downloadResult(kind)}>
      {`Download ${kind}`}
    </button>
  )
}

beforeEach(() => {
  useUi.setState({ canvasVariant: null, canvasSystemId: null })
  vi.mocked(api.contributions).mockClear()
  vi.mocked(api.inventory).mockClear()
  vi.mocked(api.resultZip).mockClear()
})

it('keeps the score on screen in a narrow panel: the indicator folds away and the variants go under the name', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}&variants=small`, <App router={false} />)
  const header = await screen.findByRole('columnheader', { name: 'Indicator' })
  expect(header).toHaveClass('hidden', '@lg:table-cell')
  const variant = withVariant.value.variants[0]
  const sign = variant.deltas[0] >= 0 ? '+' : '−'
  const line = await screen.findByText(`small: ${formatAmount(variant.scores[0].value)} (${sign}${formatAmount(Math.abs(variant.deltas[0]))})`)
  expect(line).toHaveClass('@lg:hidden')
  expect(line.closest('td')?.className).not.toContain('whitespace-nowrap')
})

it('shows one column per variant with its score and delta', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(firstMethodOf(impact.value).impact_method)}&variants=small`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('small (Δ)')).toBeInTheDocument())
  const variant = withVariant.value.variants[0]
  const half = formatAmount(variant.scores[0].value)
  const sign = variant.deltas[0] >= 0 ? '+' : '−'
  const cell = `${half} (${sign}${formatAmount(Math.abs(variant.deltas[0]))})`
  await waitFor(() => expect(screen.getByText(cell)).toBeInTheDocument())
})

it('the inventory reads under the case', async () => {
  renderAt(underCase('inventory'), <App router={false} />)
  await waitFor(() => expect(api.inventory).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ variant: 'heavy' })))
})

it('the process results, the tree and the sankey read under the case', async () => {
  const pages = [
    { page: 'processes', by: 'process' },
    { page: 'tree', by: 'path' },
    { page: 'sankey', by: 'path' },
  ]
  for (const { page, by } of pages) {
    vi.mocked(api.contributions).mockClear()
    renderAt(underCase(page), <App router={false} />)
    await waitFor(() => expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by, variant: 'heavy' })))
    expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
    cleanup()
  }
})

it('general information names the case it scored', async () => {
  renderAt(underCase('general'), <App router={false} />)
  await waitFor(() => {
    const scored = screen.getByText('Scored on').closest('div')!
    expect(within(scored).getByText('case heavy')).toBeInTheDocument()
  })
  await waitFor(() => expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by: 'process', variant: 'heavy' })))
  expect(await screen.findByText('Under case heavy')).toBeInTheDocument()
})

it('without a case no page sends one', async () => {
  const opens = [
    { page: 'general', ready: () => waitFor(() => expect(api.contributions).toHaveBeenCalled()) },
    { page: 'inventory', ready: () => waitFor(() => expect(api.inventory).toHaveBeenCalled()) },
    { page: 'impact', ready: () => screen.findByText(`Impact analysis: ${firstMethodOf(impact.value).impact_method}`) },
    { page: 'processes', ready: () => waitFor(() => expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by: 'process' }))) },
    { page: 'tree', ready: () => waitFor(() => expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by: 'path' }))) },
    { page: 'sankey', ready: () => waitFor(() => expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by: 'path' }))) },
  ]
  for (const { page, ready } of opens) {
    renderAt(underNoCase(page), <App router={false} />)
    await ready()
    for (const body of contributionsBodies()) expect(body).not.toHaveProperty('variant')
    for (const body of inventoryBodies()) expect(body).not.toHaveProperty('variant')
    expect(screen.queryByText(/^Under (case|scenario) /)).not.toBeInTheDocument()
    vi.mocked(api.contributions).mockClear()
    vi.mocked(api.inventory).mockClear()
    cleanup()
  }
})

function downloadHarness(kind: ResultKind) {
  useUi.setState({ canvasSystemId: id })
  URL.createObjectURL = vi.fn(() => 'blob:result')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  return renderAt(underCase('inventory'), <Download kind={kind} />)
}

it('the zip of the contributions carries the case the address names', async () => {
  downloadHarness('contributions')
  await waitFor(() => {
    fireEvent.click(screen.getByRole('button', { name: 'Download contributions' }))
    expect(api.resultZip).toHaveBeenCalledWith(id, 'contributions', expect.objectContaining({ by: 'process', variant: 'heavy' }))
  })
})

it('the zip of the inventory carries the case the address names', async () => {
  downloadHarness('inventory')
  await waitFor(() => {
    fireEvent.click(screen.getByRole('button', { name: 'Download inventory' }))
    expect(api.resultZip).toHaveBeenCalledWith(id, 'inventory', expect.objectContaining({ variant: 'heavy' }))
  })
})
