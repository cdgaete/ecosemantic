import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { renderAt } from './render'
import { Screens } from '@/App'
import { api } from '@/api/client'
import { useUi } from '@/store/ui'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import elementaryFlows from './fixtures/elementary_flows.json'
import backgroundProcess from './fixtures/background_process.json'
import explorerSummary from './fixtures/explorer_summary.json'
import explorerSchemes from './fixtures/explorer_schemes.json'
import explorerTree from './fixtures/explorer_tree.json'
import explorerProcesses from './fixtures/explorer_processes.json'
import explorerCompartments from './fixtures/explorer_compartments.json'
import explorerFlows from './fixtures/explorer_flows.json'
import searchProcesses from './fixtures/search_processes.json'
import type {
  Answer,
  BackgroundExchange,
  BackgroundProcess,
  ClassificationNode,
  ClassificationScheme,
  Compartment,
  DatabaseSummary,
  ElementaryFlow,
  ElementaryFlowHit,
  ListedDatabase,
  Listing,
  Method,
  MethodFamily,
  Page,
  ProcessHit,
} from '@/api/types'

const summary = explorerSummary as Answer<DatabaseSummary>
const held = databases as unknown as Answer<ListedDatabase[]>
const schemes = explorerSchemes as Answer<ClassificationScheme[]>
const tree = explorerTree as Answer<ClassificationNode[]>
const listed = explorerProcesses as Answer<Page<ProcessHit>>
const compartments = explorerCompartments as Answer<Compartment[]>
const compartmentFlows = explorerFlows as Answer<Page<ElementaryFlowHit>>
const process = backgroundProcess as Answer<BackgroundProcess>
const hits = searchProcesses as unknown as Listing<ProcessHit>
const flows = elementaryFlows as Answer<ElementaryFlow[]>
const CARBON = (process.value.exchanges ?? []).find((exchange) => exchange.flow === 'Carbon dioxide, fossil')!.input!.id
const SUPPLIER = '4a018168-2ca8-56de-a7f7-c7ce8f6a5040_81c36885-6d13-58e3-ba9a-869123a0f84c'
const PUBLICATION = 'https://ecoquery.ecoinvent.org/3.12/cutoff/dataset/275867/documentation'

const OLCA_METHOD: Method = {
  id: 'm_olca',
  tuple: ['fixture', 'IPCC 2021', 'climate change', 'climate change'],
  spec: 'fixture > IPCC 2021 > climate change > climate change',
  unit: 'kg CO2-Eq',
  impact_method: 'IPCC 2021',
  impact_category: 'climate change',
  indicator: 'climate change',
}
const METHOD_FAMILIES: Answer<MethodFamily[]> = {
  hint: null,
  value: [{ name: 'IPCC 2021', categories: [{ name: 'climate change', indicators: [OLCA_METHOD] }] }],
  view_url: null,
}

interface UnderParams {
  node: string
  query?: string
  limit?: number
  cursor?: string
  item?: string
}

interface SearchParams {
  query: string
  limit?: number
  cursor?: string
}

interface FlowsParams {
  sub_compartment?: string
  query?: string
  limit?: number
  cursor?: string
  item?: string
}

type SummaryRead = (database: string) => Promise<Answer<DatabaseSummary>>
type SchemesRead = (database: string) => Promise<Answer<ClassificationScheme[]>>
type TreeRead = (database: string, scheme: string) => Promise<Answer<ClassificationNode[]>>
type SearchRead = (database: string, params: SearchParams) => Promise<Listing<ProcessHit>>
type MethodsRead = (database: string) => Promise<Answer<MethodFamily[]>>

const readSummary = vi.fn<SummaryRead>(async () => summary)
const readSchemes = vi.fn<SchemesRead>(async () => schemes)
const readTree = vi.fn<TreeRead>(async () => tree)
type UnderRead = (database: string, scheme: string, params: UnderParams) => Promise<Answer<Page<ProcessHit>>>

const readUnderNode = vi.fn<UnderRead>(async () => listed)
const readSearch = vi.fn<SearchRead>(async () => hits)
type CompartmentsRead = (database: string) => Promise<Answer<Compartment[]>>
type FlowsRead = (database: string, compartment: string, params: FlowsParams) => Promise<Answer<Page<ElementaryFlowHit>>>

const readCompartments = vi.fn<CompartmentsRead>(async () => compartments)
const readFlowsIn = vi.fn<FlowsRead>(async () => compartmentFlows)
const readMethodTree = vi.fn<MethodsRead>(async () => METHOD_FAMILIES)

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      elementaryFlows: vi.fn(async (_database: string, ids: string[]) => ({ ...elementaryFlow, value: ids.map((id) => ({ ...elementaryFlow.value, ref: { ...elementaryFlow.value.ref, id } })) })),
      elementaryFlow: vi.fn(),
      backgroundProcess: vi.fn(async () => process),
      summary: (database: string) => readSummary(database),
      schemes: (database: string) => readSchemes(database),
      tree: (database: string, scheme: string) => readTree(database, scheme),
      underNode: (database: string, scheme: string, params: UnderParams) => readUnderNode(database, scheme, params),
      searchProcesses: (database: string, params: SearchParams) => readSearch(database, params),
      compartments: (database: string) => readCompartments(database),
      flowsIn: (database: string, compartment: string, params: FlowsParams) => readFlowsIn(database, compartment, params),
      methodTree: (database: string) => readMethodTree(database),
    },
  }
})

function Address() {
  const location = useLocation()
  return <output data-testid="address">{location.search}</output>
}

const params = () => new URLSearchParams(screen.getByTestId('address').textContent ?? '')

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
  readCompartments.mockReset().mockResolvedValue(compartments)
  readFlowsIn.mockReset().mockResolvedValue(compartmentFlows)
  readMethodTree.mockReset().mockResolvedValue(METHOD_FAMILIES)
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

const sectionBarTitle = async () => {
  const nav = await screen.findByRole('navigation', { name: 'Sections' })
  const header = nav.closest('header')
  if (header === null) throw new Error('the section bar holds no title')
  return within(within(header).getByRole('heading', { level: 1 }))
}

it('shows the version alone in the section bar where the database has no revision', async () => {
  renderAt('/databases/fixture/datasets', <Screens />)
  const title = await sectionBarTitle()
  expect(await title.findByText(held.value[0].version)).toBeInTheDocument()
})

it('shows the revision beside the version in the section bar', async () => {
  const [plain, revised] = held.value
  vi.mocked(api.databases).mockResolvedValue({
    ...held,
    value: [{ ...plain, version: '1.2026-09.0', revision: 1 }, revised],
  })
  try {
    renderAt('/databases/fixture/datasets', <Screens />)
    const title = await sectionBarTitle()
    expect(await title.findByText('1.2026-09.0 · revision 1')).toBeInTheDocument()
  } finally {
    vi.mocked(api.databases).mockResolvedValue(held)
  }
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
  fireEvent.click(await rows.findByRole('button', { name: 'Next page' }))
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].cursor).toBe('cursor-1'))
  fireEvent.change(rows.getByLabelText('Filter the processes'), { target: { value: 'steel' } })
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].query).toBe('steel'))
  expect(readUnderNode.mock.calls.at(-1)?.[2].cursor).toBeUndefined()
})

it('asks for the flows once typing pauses in the flows filter', async () => {
  renderAt('/databases/fixture/flows?compartment=air', <Screens />)
  const rows = within(await screen.findByRole('region', { name: 'Elementary flows' }))
  await waitFor(() => expect(rows.getByText('Particulate matter')).toBeInTheDocument())
  readFlowsIn.mockClear()
  const input = rows.getByLabelText('Filter the flows')
  const typed = 'methane, fossil'
  for (let end = 1; end <= typed.length; end += 1) {
    fireEvent.change(input, { target: { value: typed.slice(0, end) } })
  }
  await waitFor(() => expect(readFlowsIn).toHaveBeenCalledTimes(1))
  expect(readFlowsIn.mock.calls[0][2].query).toBe(typed)
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
  const link = within(inputs).getByRole('link', { name: 'electricity production · GLO' })
  expect(link).toHaveAttribute('href', `/databases/fixture/processes/${SUPPLIER}`)
})

it("names a background input's supplier with the location its dataset is at", async () => {
  const template = (process.value.exchanges ?? []).find((exchange) => exchange.type === 'product' && !exchange.reference)!
  const wind: BackgroundExchange = { ...template, flow: 'electricity, at wind farm', supplier: 'Electricity, at wind farm', supplier_location: 'CH' }
  vi.mocked(api.backgroundProcess).mockResolvedValue({
    ...process,
    value: { ...process.value, exchanges: [...(process.value.exchanges ?? []), wind] },
  })
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const inputs = shown.getByText('Inputs').closest('section')!
  const link = within(inputs).getByRole('link', { name: 'Electricity, at wind farm · CH' })
  expect(link).toHaveAttribute('href', `/databases/fixture/processes/${SUPPLIER}`)
})

it("shows an elementary flow's provider as its flow type and compartment", async () => {
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const outputs = shown.getByText('Outputs').closest('section')!
  const row = within(outputs).getByText('Carbon dioxide, fossil').closest('tr')!
  await waitFor(() => expect(row.textContent).toContain(`${elementaryFlow.value.flow_type} · ${elementaryFlow.value.compartment}`))
})

it('reads the flows of a process in one request, showing each row its own flow and naming one the answer lacks', async () => {
  const carbon = flows.value.find((flow) => flow.name === 'Carbon dioxide, fossil')!
  const river = flows.value.find((flow) => flow.name === 'Water, river')!
  const template = (process.value.exchanges ?? []).find((exchange) => exchange.type === 'elementary')!
  const water: BackgroundExchange = { ...template, amount: 0.002, flow: river.name, input: { database: river.ref.database, id: river.ref.id, kind: 'elementary_flow' }, side: 'input', unit: river.unit }
  const missing: BackgroundExchange = { ...water, flow: 'Ammonia', input: { database: river.ref.database, id: 'no-such-flow', kind: 'elementary_flow' } }
  vi.mocked(api.backgroundProcess).mockResolvedValue({
    ...process,
    value: { ...process.value, exchanges: [...(process.value.exchanges ?? []), water, missing] },
  })
  const read = vi.fn(async (_database: string, ids: string[]) => ({
    ...flows,
    value: flows.value.filter((flow) => ids.includes(flow.ref.id)),
  }))
  vi.mocked(api.elementaryFlows).mockImplementationOnce(read)
  renderAt(`/databases/fixture/processes/${process.value.ref.id}`, <Screens />)
  const shown = await detail('steel production')
  const outputs = shown.getByText('Outputs').closest('section')!
  const carbonRow = within(outputs).getByText(carbon.name).closest('tr')!
  await waitFor(() => expect(carbonRow.textContent).toContain(`${carbon.flow_type} · ${carbon.compartment}`))
  const inputs = shown.getByText('Inputs').closest('section')!
  const waterRow = within(inputs).getByText(river.name).closest('tr')!
  expect(waterRow.textContent).toContain(`${river.flow_type} · ${river.compartment}`)
  expect(read).toHaveBeenCalledTimes(1)
  expect(read).toHaveBeenCalledWith(river.ref.database, [...(process.value.exchanges ?? []).filter((exchange) => exchange.type === 'elementary').map((exchange) => exchange.input!.id), river.ref.id, 'no-such-flow'])
  expect(api.elementaryFlow).not.toHaveBeenCalled()
  expect(await shown.findByText(`Ammonia: no flow 'no-such-flow' in '${river.ref.database}'`)).toBeInTheDocument()
  expect(within(inputs).getByText(river.name).closest('tr')!.textContent).toContain(`${river.flow_type} · ${river.compartment}`)
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
    supplier_location: null,
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

it('opens an indicator whose name is its own category from the methods list', async () => {
  renderAt('/databases/fixture/methods', <Screens />)
  const nodes = within(await screen.findByRole('navigation', { name: 'Impact methods' }))
  fireEvent.click(await nodes.findByRole('button', { name: /^IPCC 2021/ }))
  fireEvent.click(await nodes.findByRole('button', { name: /^climate change/ }))
  const rows = within(await screen.findByRole('region', { name: 'Indicators' }))
  const link = await rows.findByRole('link', { name: 'climate change' })
  const carried = new URLSearchParams(link.getAttribute('href')?.split('?')[1] ?? '')
  expect(carried.get('item')).toBe('m_olca')
  expect(carried.get('family')).toBe('IPCC 2021')
  expect(carried.get('category')).toBe('climate change')
})

const STEEL = '4f4cd935-e76c-526e-ab03-7655288e357a_492f207c-0a66-5f26-acf9-c12ac5accb4c'

it("the open item's row is marked", async () => {
  const opened = renderAt(`/databases/fixture/datasets?node=24&item=${STEEL}`, <Screens />)
  const rows = await listing()
  const row = (await rows.findByRole('link', { name: 'steel production' })).closest('tr')!
  expect(row).toHaveAttribute('aria-current', 'true')
  expect(row).toHaveClass('bg-selected')
  opened.unmount()

  const closed = renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const plain = await listing()
  await plain.findByText('steel production')
  expect(plain.getAllByRole('row').filter((entry) => entry.getAttribute('aria-current') === 'true')).toEqual([])
  closed.unmount()

  renderAt('/databases/fixture/datasets?node=24&item=no-such-process', <Screens />)
  const elsewhere = await listing()
  await elsewhere.findByText('steel production')
  expect(elsewhere.getAllByRole('row').filter((entry) => entry.getAttribute('aria-current') === 'true')).toEqual([])
})

it("a filtered listing names what its filter keeps beside the node's count", async () => {
  const plain = renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const unfiltered = await listing()
  await unfiltered.findByText('steel production')
  expect(unfiltered.getByText('3')).toBeInTheDocument()
  expect(unfiltered.queryByText('1 of 3')).toBeNull()
  plain.unmount()

  readUnderNode.mockResolvedValue({
    ...listed,
    value: { ...listed.value, items: listed.value.items.filter((hit) => hit.name === 'steel production'), total: 1 },
  })
  renderAt('/databases/fixture/datasets?node=24&q=steel', <Screens />)
  const narrowed = await listing()
  expect(await narrowed.findByText('1 of 3')).toBeInTheDocument()
  expect(narrowed.queryByText('3')).toBeNull()
})

it('the indicators table is headed by its family and category', async () => {
  renderAt('/databases/fixture/methods', <Screens />)
  const nodes = within(await screen.findByRole('navigation', { name: 'Impact methods' }))
  fireEvent.click(await nodes.findByRole('button', { name: /^IPCC 2021/ }))
  fireEvent.click(await nodes.findByRole('button', { name: /^climate change/ }))
  const rows = within(await screen.findByRole('region', { name: 'Indicators' }))
  expect(await rows.findByRole('heading', { name: /^IPCC 2021 › climate change/ })).toBeInTheDocument()
})

it('a process opened by its address opens the tree to its node and lists it', async () => {
  renderAt(
    `/databases/fixture/processes/${STEEL}`,
    <>
      <Screens />
      <Address />
    </>,
  )
  const nodes = await classification()
  await waitFor(() => expect(nodes.getByRole('button', { name: 'Collapse 24' })).toBeInTheDocument())
  expect(nodes.getByRole('button', { name: 'Collapse 241' })).toBeInTheDocument()
  expect(nodes.getByRole('button', { name: /^2410/ })).toHaveAttribute('aria-current', 'true')
  await waitFor(() => expect(params().get('node')).toBe('2410'))
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2]).toMatchObject({ node: '2410', item: STEEL }))
  const rows = await listing()
  const row = (await rows.findByRole('link', { name: 'steel production' })).closest('tr')!
  expect(row).toHaveAttribute('aria-current', 'true')
})

it('the person can collapse the branch that holds the open node', async () => {
  renderAt(`/databases/fixture/processes/${STEEL}`, <Screens />)
  const nodes = await classification()
  await waitFor(() => expect(nodes.getByRole('button', { name: 'Collapse 24' })).toBeInTheDocument())
  fireEvent.click(nodes.getByRole('button', { name: 'Collapse 24' }))
  await waitFor(() => expect(nodes.queryByRole('button', { name: /^241/ })).toBeNull())
  expect(await nodes.findByRole('button', { name: 'Expand 24' })).toBeInTheDocument()
  expect(nodes.queryByRole('button', { name: /^2410/ })).toBeNull()
})

it('a process with no value under the chosen scheme leaves the tree as it is', async () => {
  readTree.mockResolvedValue({ hint: null, value: [], view_url: null })
  renderAt(
    `/databases/fixture/processes/${STEEL}?scheme=CPC`,
    <>
      <Screens />
      <Address />
    </>,
  )
  const shown = await detail('steel production')
  const isic = shown.getByText('ISIC rev.4 ecoinvent').closest('tr')!
  const eco = shown.getByText('EcoSpold01Categories').closest('tr')!
  expect(within(isic).getByRole('link')).toBeInTheDocument()
  expect(within(eco).getByRole('link')).toBeInTheDocument()
  await waitFor(() => expect(readTree.mock.calls.at(-1)?.[1]).toBe('CPC'))
  expect(await screen.findByText('Choose a node of the classification to list its processes.')).toBeInTheDocument()
  expect(params().has('node')).toBe(false)
  expect(readUnderNode).not.toHaveBeenCalled()
})

it('a flow opened by its address opens its compartment and sub-compartment', async () => {
  const flow = elementaryFlow as Answer<ElementaryFlow>
  vi.mocked(api.elementaryFlow).mockResolvedValue(flow)
  renderAt(
    `/databases/fixture/flows/${flow.value.ref.id}`,
    <>
      <Screens />
      <Address />
    </>,
  )
  const shown = await detail('Water, river')
  expect(shown.getByText('in water')).toBeInTheDocument()
  const nodes = within(await screen.findByRole('navigation', { name: 'Compartments' }))
  await waitFor(() => expect(nodes.getByRole('button', { name: 'Collapse natural resource' })).toBeInTheDocument())
  expect(nodes.getByRole('button', { name: /^in water/ })).toHaveAttribute('aria-current', 'true')
  await waitFor(() => expect(params().get('compartment')).toBe('natural resource'))
  expect(params().get('sub')).toBe('in water')
  await waitFor(() =>
    expect(readFlowsIn.mock.calls.at(-1)).toEqual([
      'fixture',
      'natural resource',
      expect.objectContaining({ sub_compartment: 'in water', item: flow.value.ref.id }),
    ]),
  )
})

it('an indicator opened by its address opens its family and category', async () => {
  renderAt(
    '/databases/fixture/methods/m_olca',
    <>
      <Screens />
      <Address />
    </>,
  )
  const nodes = within(await screen.findByRole('navigation', { name: 'Impact methods' }))
  await waitFor(() => expect(nodes.getByRole('button', { name: 'Collapse IPCC 2021' })).toBeInTheDocument())
  expect(nodes.getByRole('button', { name: /^climate change/ })).toHaveAttribute('aria-current', 'true')
  await waitFor(() => expect(params().get('family')).toBe('IPCC 2021'))
  expect(params().get('category')).toBe('climate change')
})

it("a listing is asked for its cursor's page once the person pages", async () => {
  readUnderNode.mockResolvedValue({ ...listed, value: { ...listed.value, has_more: true, next_cursor: 'cursor-1' } })
  renderAt(`/databases/fixture/datasets?node=24&item=${STEEL}`, <Screens />)
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].item).toBe(STEEL))
  const rows = await listing()
  fireEvent.click(await rows.findByRole('button', { name: 'Next page' }))
  await waitFor(() => expect(readUnderNode.mock.calls.at(-1)?.[2].cursor).toBe('cursor-1'))
  expect(readUnderNode.mock.calls.at(-1)?.[2].item).toBeUndefined()
})
