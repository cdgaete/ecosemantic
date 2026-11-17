import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { Screens } from '@/App'
import { api } from '@/api/client'
import { useUi } from '@/store/ui'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import backgroundProcess from './fixtures/background_process.json'
import explorerSummary from './fixtures/explorer_summary.json'
import explorerSchemes from './fixtures/explorer_schemes.json'
import explorerTree from './fixtures/explorer_tree.json'
import explorerProcesses from './fixtures/explorer_processes.json'
import searchProcesses from './fixtures/search_processes.json'
import type {
  Answer,
  BackgroundExchange,
  BackgroundProcess,
  ClassificationNode,
  ClassificationScheme,
  DatabaseSummary,
  Listing,
  Page,
  ProcessHit,
} from '@/api/types'

const summary = explorerSummary as Answer<DatabaseSummary>
const schemes = explorerSchemes as Answer<ClassificationScheme[]>
const tree = explorerTree as Answer<ClassificationNode[]>
const listed = explorerProcesses as Answer<Page<ProcessHit>>
const process = backgroundProcess as Answer<BackgroundProcess>
const hits = searchProcesses as unknown as Listing<ProcessHit>
const CARBON = (process.value.exchanges ?? []).find((exchange) => exchange.flow === 'Carbon dioxide, fossil')!.input!.id
const SUPPLIER = '4a018168-2ca8-56de-a7f7-c7ce8f6a5040_81c36885-6d13-58e3-ba9a-869123a0f84c'
const PUBLICATION = 'https://ecoquery.ecoinvent.org/3.12/cutoff/dataset/275867/documentation'

interface UnderParams {
  node: string
  query?: string
  limit?: number
  cursor?: string
}

interface SearchParams {
  query: string
  limit?: number
  cursor?: string
}

type SummaryRead = (database: string) => Promise<Answer<DatabaseSummary>>
type SchemesRead = (database: string) => Promise<Answer<ClassificationScheme[]>>
type TreeRead = (database: string, scheme: string) => Promise<Answer<ClassificationNode[]>>
type SearchRead = (database: string, params: SearchParams) => Promise<Listing<ProcessHit>>

const readSummary = vi.fn<SummaryRead>(async () => summary)
const readSchemes = vi.fn<SchemesRead>(async () => schemes)
const readTree = vi.fn<TreeRead>(async () => tree)
type UnderRead = (database: string, scheme: string, params: UnderParams) => Promise<Answer<Page<ProcessHit>>>

const readUnderNode = vi.fn<UnderRead>(async () => listed)
const readSearch = vi.fn<SearchRead>(async () => hits)

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      elementaryFlow: vi.fn(async () => elementaryFlow),
      backgroundProcess: vi.fn(async () => process),
      summary: (database: string) => readSummary(database),
      schemes: (database: string) => readSchemes(database),
      tree: (database: string, scheme: string) => readTree(database, scheme),
      underNode: (database: string, scheme: string, params: UnderParams) => readUnderNode(database, scheme, params),
      searchProcesses: (database: string, params: SearchParams) => readSearch(database, params),
    },
  }
})

const sectionBar = async () => within(await screen.findByRole('navigation', { name: 'Sections' }))
const listing = async () => within(await screen.findByRole('region', { name: 'Processes' }))
const detail = async (name: string) => within(await screen.findByRole('region', { name }))
const classification = async () => within(await screen.findByRole('navigation', { name: 'Classification' }))

beforeEach(() => {
  useUi.setState({ explorerSchemes: {}, collapsed: {}, canvasSystemId: null })
  vi.mocked(api.backgroundProcess).mockResolvedValue(process)
  readSummary.mockReset().mockResolvedValue(summary)
  readSchemes.mockReset().mockResolvedValue(schemes)
  readTree.mockReset().mockResolvedValue(tree)
  readUnderNode.mockReset().mockResolvedValue(listed)
  readSearch.mockReset().mockResolvedValue(hits)
})

it('opens a database on its first scheme with the counts in the section bar', async () => {
  renderAt('/databases/fixture/datasets', <Screens />)
  const bar = await sectionBar()
  const datasets = await bar.findByRole('link', { name: 'Datasets 12' })
  expect(datasets).toHaveAttribute('href', '/databases/fixture/datasets')
  expect(datasets).toHaveAttribute('aria-current', 'page')
  expect(bar.getByRole('link', { name: 'Elementary flows 4' })).toHaveAttribute('href', '/databases/fixture/flows')
  expect(bar.getByRole('link', { name: 'Impact methods 2' })).toBeInTheDocument()
  expect(bar.getByRole('link', { name: 'Units 3' })).toBeInTheDocument()
  expect(bar.getByRole('link', { name: 'Locations 1' })).toBeInTheDocument()
  expect(await screen.findByLabelText('Scheme')).toHaveValue('ISIC rev.4 ecoinvent')
  await waitFor(() => expect(readTree.mock.calls.at(-1)?.[1]).toBe('ISIC rev.4 ecoinvent'))
})

it('walks the ISIC tree to node 24 and lists its three processes', async () => {
  renderAt('/databases/fixture/datasets', <Screens />)
  const nodes = await classification()
  fireEvent.click(await nodes.findByRole('button', { name: /^24 Manufacture of basic metals/ }))
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].node).toBe('24'))
  const rows = await listing()
  await waitFor(() => expect(rows.getByText('aluminium production')).toBeInTheDocument())
  expect(rows.getByText('copper production')).toBeInTheDocument()
  expect(rows.getByText('steel production')).toBeInTheDocument()
  expect(rows.getByText('3')).toBeInTheDocument()
  expect(rows.getByText('Manufacture of basic metals')).toBeInTheDocument()
})

it('keeps only the branches a filter holds, at every level of the tree', async () => {
  renderAt('/databases/fixture/datasets', <Screens />)
  const nodes = await classification()
  fireEvent.change(nodes.getByLabelText('Filter the tree'), { target: { value: 'iron' } })
  await waitFor(() => expect(nodes.getAllByRole('button').map((button) => button.firstElementChild?.textContent)).toEqual(['24', '241', '2410']))
  expect(nodes.queryByRole('button', { name: /^242 / })).toBeNull()
  expect(nodes.queryByRole('button', { name: /^35 / })).toBeNull()
})

it('narrows the open node with its filter and starts again at the first page when the filter changes', async () => {
  readUnderNode.mockResolvedValue({ ...listed, value: { ...listed.value, has_more: true, next_cursor: 'cursor-1' } })
  renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const rows = await listing()
  await waitFor(() => expect(rows.getByText('aluminium production')).toBeInTheDocument())
  fireEvent.click(rows.getByRole('button', { name: 'More…' }))
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].cursor).toBe('cursor-1'))
  fireEvent.change(rows.getByLabelText('Filter the processes'), { target: { value: 'steel' } })
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].query).toBe('steel'))
  expect(readUnderNode.mock.calls.at(-1)?.[2].cursor).toBeUndefined()
})

it('opens a process from the table with one row per scheme and links each value to its node', async () => {
  renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const rows = await listing()
  fireEvent.click(await rows.findByRole('link', { name: 'steel production' }))
  const shown = await detail('steel production')
  const isic = shown.getByText('ISIC rev.4 ecoinvent').closest('tr')!
  const link = within(isic).getByRole('link')
  const carried = new URLSearchParams(link.getAttribute('href')?.split('?')[1] ?? '')
  expect(carried.get('scheme')).toBe('ISIC rev.4 ecoinvent')
  expect(carried.get('value')).toBe('ISIC rev.4 ecoinvent: 2410:Manufacture of basic iron and steel')
  expect(link).toHaveTextContent('2410:Manufacture of basic iron and steel')
  const eco = shown.getByText('EcoSpold01Categories').closest('tr')!
  const ecoCarried = new URLSearchParams(within(eco).getByRole('link').getAttribute('href')?.split('?')[1] ?? '')
  expect(ecoCarried.get('scheme')).toBe('EcoSpold01Categories')
  expect(ecoCarried.get('value')).toBe('EcoSpold01Categories: metals/production')
  fireEvent.click(link)
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].node).toBe('2410'))
  const opened = await listing()
  expect(await opened.findByText('steel production')).toBeInTheDocument()
  expect(opened.getByText('2410')).toBeInTheDocument()
})

it('links an elementary flow of a detail to the flow in the database the detail is shown for', async () => {
  renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const rows = await listing()
  fireEvent.click(await rows.findByRole('link', { name: 'steel production' }))
  const shown = await detail('steel production')
  const link = shown.getByText('Carbon dioxide, fossil').closest('a')
  expect(link).toHaveAttribute('href', `/databases/fixture/flows/${CARBON}`)
})

it('says a database carries no classification and offers the whole-database search', async () => {
  readSchemes.mockResolvedValue({ hint: null, value: [], view_url: null })
  renderAt('/databases/looped/datasets', <Screens />)
  expect(await screen.findByText(/carries no classification/)).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Classification' })).toBeNull()
  expect(screen.queryByLabelText('Scheme')).toBeNull()
  const rows = await listing()
  fireEvent.change(rows.getByLabelText('Filter the processes'), { target: { value: 'steel' } })
  await waitFor(() => expect(readSearch.mock.calls.at(-1)?.[1].query).toBe('steel'))
  expect(await rows.findByText('steel production')).toBeInTheDocument()
})

it('opens /databases/fixture/processes/:ref on the datasets section with that process', async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  expect(shown.getByText('GLO')).toBeInTheDocument()
  const bar = await sectionBar()
  expect(bar.getByRole('link', { name: 'Datasets 12' })).toHaveAttribute('aria-current', 'page')
  expect(await screen.findByLabelText('Scheme')).toHaveValue('ISIC rev.4 ecoinvent')
})

it('remembers the scheme chosen for a database', async () => {
  const first = renderAt('/databases/fixture/datasets', <Screens />)
  fireEvent.change(await screen.findByLabelText('Scheme'), { target: { value: 'CPC' } })
  await waitFor(() => expect(readTree.mock.calls.at(-1)?.[1]).toBe('CPC'))
  first.unmount()
  const second = renderAt('/databases/fixture/datasets', <Screens />)
  expect(await screen.findByLabelText('Scheme')).toHaveValue('CPC')
  second.unmount()
  renderAt('/databases/looped/datasets', <Screens />)
  expect(await screen.findByLabelText('Scheme')).toHaveValue('ISIC rev.4 ecoinvent')
})

it('takes the main area whatever system the canvas holds', async () => {
  useUi.setState({ canvasSystemId: systems.value[0].id })
  const view = renderAt('/databases/fixture/datasets', <Screens />)
  const bar = await sectionBar()
  expect(await bar.findByRole('link', { name: 'Datasets 12' })).toHaveAttribute('aria-current', 'page')
  expect(view.container.querySelector('.react-flow')).toBeNull()
})

it('opens /databases/fixture/search/processes on the whole-database search', async () => {
  renderAt('/databases/fixture/search/processes?q=steel', <Screens />)
  await waitFor(() => expect(readSearch.mock.calls.at(-1)?.[1].query).toBe('steel'))
  const rows = await listing()
  expect(await rows.findByText('steel production')).toBeInTheDocument()
  expect(rows.getByLabelText('Filter the processes')).toHaveValue('steel')
  expect(readUnderNode).not.toHaveBeenCalled()
  const bar = await sectionBar()
  expect(bar.getByRole('link', { name: 'Datasets 12' })).toHaveAttribute('aria-current', 'page')
})

it("opens a dataset's publication link in a new tab", async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue({ ...process, value: { ...process.value, url: PUBLICATION } })
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const link = await screen.findByRole('link', { name: PUBLICATION })
  expect(link).toHaveAttribute('href', PUBLICATION)
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noreferrer')
})

it('shows no publication link for a dataset that carries none', async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  expect(shown.getByText('Reference product')).toBeInTheDocument()
  expect(shown.queryByRole('link', { name: /ecoquery/ })).toBeNull()
})

it('shows an empty Location fact for a dataset that names no location', async () => {
  vi.mocked(api.backgroundProcess).mockResolvedValue({ ...process, value: { ...process.value, location: null } })
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const label = shown.getByText('Location')
  expect(label.nextElementSibling?.textContent).toBe('')
  expect(shown.queryByText('null')).not.toBeInTheDocument()
})

it('shows the exchanges as an Inputs table and an Outputs table of flow, amount, unit and provider', async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const inputs = shown.getByText('Inputs').closest('section')!
  const outputs = shown.getByText('Outputs').closest('section')!
  for (const table of [inputs, outputs]) {
    for (const header of ['Flow', 'Amount', 'Unit', 'Provider']) {
      expect(within(table).getByText(header)).toBeInTheDocument()
    }
    expect(within(table).queryByText('Type')).not.toBeInTheDocument()
  }
  expect(inputs.textContent).toContain('electricity')
  expect(outputs.textContent).toContain('steel')
  expect(inputs.textContent).not.toContain('steel')
})

it("puts the reference output first in Outputs, in bold, and links a product to its supplier's dataset", async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const outputs = shown.getByText('Outputs').closest('section')!
  const rows = within(outputs).getAllByRole('row').slice(1)
  expect(rows[0].textContent).toContain('steel')
  expect(rows[0].className).toContain('font-semibold')
  expect(rows.slice(1).filter((row) => row.className.includes('font-semibold'))).toEqual([])
  const inputs = shown.getByText('Inputs').closest('section')!
  const link = within(inputs).getByRole('link', { name: 'electricity production' })
  expect(link).toHaveAttribute('href', `/databases/fixture/processes/${SUPPLIER}`)
})

it("shows an elementary flow's provider as its flow type and compartment", async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const outputs = shown.getByText('Outputs').closest('section')!
  const row = within(outputs).getByText('Carbon dioxide, fossil').closest('tr')!
  await waitFor(() => expect(row.textContent).toContain(`${elementaryFlow.value.flow_type} · ${elementaryFlow.value.compartment}`))
})

it('shows an input the install cut off in Inputs with its reason and no provider', async () => {
  const cutOff: BackgroundExchange = {
    amount: 0.25,
    cut_off: 'no provider for the input',
    flow: 'sand',
    input: null,
    reference: false,
    side: 'input',
    supplier: null,
    type: 'product',
    unit: 'kilogram',
  }
  vi.mocked(api.backgroundProcess).mockResolvedValue({
    ...process,
    value: { ...process.value, exchanges: [...(process.value.exchanges ?? []), cutOff] },
  })
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const inputs = shown.getByText('Inputs').closest('section')!
  const reason = within(inputs).getByText('cut off: no provider for the input')
  expect(reason).toHaveClass('text-muted-foreground')
  const row = reason.closest('tr')!
  expect(row.textContent).toContain('sand')
  expect(row.textContent).toContain('0.25')
  expect(within(row).queryByRole('link')).not.toBeInTheDocument()
})
