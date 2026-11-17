import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { Screens } from '@/App'
import { useUi } from '@/store/ui'
import type {
  Answer,
  Compartment,
  DatabaseSummary,
  ElementaryFlowHit,
  Listing,
  Method,
  MethodFamily,
  ProcessHit,
  Term,
  VocabularyKind,
} from '@/api/types'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import explorerSummary from './fixtures/explorer_summary.json'
import explorerSchemes from './fixtures/explorer_schemes.json'
import explorerTree from './fixtures/explorer_tree.json'
import explorerCompartments from './fixtures/explorer_compartments.json'
import explorerMethods from './fixtures/explorer_methods.json'
import listProcesses from './fixtures/search_processes.json'
import listFlows from './fixtures/search_elementary_flows.json'
import listMethods from './fixtures/search_methods.json'
import vocabularyCompartments from './fixtures/vocabulary_compartments.json'
import { renderAt } from './render'

const summary = explorerSummary as Answer<DatabaseSummary>
const schemes = explorerSchemes as Answer<never>
const tree = explorerTree as Answer<never>
const compartments = explorerCompartments as Answer<Compartment[]>
const families = explorerMethods as Answer<MethodFamily[]>

const flowsPage: Listing<ElementaryFlowHit> = {
  ...(listFlows as unknown as Listing<ElementaryFlowHit>),
  has_more: true,
  next_cursor: 'cursor-1',
}

const processesPage: Listing<ProcessHit> = {
  ...(listProcesses as unknown as Listing<ProcessHit>),
  has_more: true,
  next_cursor: 'proc-cursor-1',
}

const methodsPage: Listing<Method> = {
  ...(listMethods as unknown as Listing<Method>),
  has_more: true,
  next_cursor: 'm-cursor-1',
}

const units: Answer<Term[]> = {
  hint: null,
  value: [
    { value: 'kilogram', detail: null },
    { value: 'kilowatt hour', detail: null },
  ],
  view_url: null,
}

const locations: Answer<Term[]> = { hint: null, value: [{ value: 'GLO', detail: 'Global' }], view_url: null }

interface FlowsParams {
  query: string
  compartment?: string
  limit?: number
  cursor?: string
}

interface ProcessesParams {
  query: string
  location?: string
  unit?: string
  limit?: number
  cursor?: string
}

interface MethodsParams {
  query: string
  limit?: number
  cursor?: string
}

type VocabularyRead = (database: string, kind: VocabularyKind) => Promise<Answer<Term[]>>
type FlowSearchRead = (database: string, params: FlowsParams) => Promise<Listing<ElementaryFlowHit>>
type ProcessSearchRead = (database: string, params: ProcessesParams) => Promise<Listing<ProcessHit>>
type MethodSearchRead = (database: string, params: MethodsParams) => Promise<Listing<Method>>

const readVocabulary = vi.fn<VocabularyRead>(async (_database, kind) =>
  kind === 'units' ? units : kind === 'locations' ? locations : (vocabularyCompartments as Answer<Term[]>),
)
const readSearchFlows = vi.fn<FlowSearchRead>(async () => flowsPage)
const readSearchProcesses = vi.fn<ProcessSearchRead>(async () => processesPage)
const readSearchMethods = vi.fn<MethodSearchRead>(async () => methodsPage)

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      summary: vi.fn(async () => summary),
      schemes: vi.fn(async () => schemes),
      tree: vi.fn(async () => tree),
      compartments: vi.fn(async () => compartments),
      methodTree: vi.fn(async () => families),
      vocabulary: (database: string, kind: VocabularyKind) => readVocabulary(database, kind),
      searchElementaryFlows: (database: string, params: FlowsParams) => readSearchFlows(database, params),
      searchProcesses: (database: string, params: ProcessesParams) => readSearchProcesses(database, params),
      searchMethods: (database: string, params: MethodsParams) => readSearchMethods(database, params),
    },
  }
})

function Address() {
  const location = useLocation()
  return <output data-testid="address">{location.search}</output>
}

const listing = async (name: string) => within(await screen.findByRole('region', { name }))

beforeEach(() => {
  useUi.setState({ explorerSchemes: {} })
  readVocabulary.mockReset().mockImplementation(async (_database, kind) =>
    kind === 'units' ? units : kind === 'locations' ? locations : (vocabularyCompartments as Answer<Term[]>),
  )
  readSearchFlows.mockReset().mockResolvedValue(flowsPage)
  readSearchProcesses.mockReset().mockResolvedValue(processesPage)
  readSearchMethods.mockReset().mockResolvedValue(methodsPage)
})

it('drops the cursor when the compartment filter changes after paging with More', async () => {
  renderAt('/databases/fixture/search/elementary-flows?q=flow', <Screens />)
  const rows = await listing('Elementary flows')
  await waitFor(() => expect(rows.getByText('Carbon dioxide, fossil')).toBeInTheDocument())
  fireEvent.click(await rows.findByRole('button', { name: 'More…' }))
  await waitFor(() => expect(readSearchFlows.mock.calls.at(-1)?.[1].cursor).toBe('cursor-1'))
  fireEvent.change(screen.getByLabelText('Compartment'), { target: { value: 'air' } })
  await waitFor(() => expect(readSearchFlows.mock.calls.at(-1)?.[1].compartment).toBe('air'))
  expect(readSearchFlows.mock.calls.at(-1)?.[1].cursor).toBeUndefined()
})

it("shows the tool's hint under a results table that has rows", async () => {
  readSearchProcesses.mockResolvedValue({ ...processesPage, has_more: false, next_cursor: null, hint: 'Nearest matches by name; add a location to narrow them.' })
  renderAt('/databases/fixture/search/processes?q=steel', <Screens />)
  const rows = await listing('Processes')
  await waitFor(() => expect(rows.getByText('steel production')).toBeInTheDocument())
  expect(screen.getByText('Nearest matches by name; add a location to narrow them.')).toBeInTheDocument()
})

it('draws the hits of the search its address names, with the filters it carries', async () => {
  renderAt('/databases/fixture/search/processes?q=steel&location=GLO', <Screens />)
  const rows = await listing('Processes')
  await waitFor(() => expect(rows.getByText('steel production')).toBeInTheDocument())
  expect(readSearchProcesses.mock.calls.at(-1)?.[1]).toMatchObject({ query: 'steel', location: 'GLO' })
  expect(rows.getByLabelText('Filter the processes')).toHaveValue('steel')
  await waitFor(() => expect(screen.getByLabelText('Location')).toHaveValue('GLO'))
})

it('writes its query and its filters into the address, and drops the page on a new query', async () => {
  renderAt(
    '/databases/fixture/search/processes?q=old&cursor=proc-cursor-1',
    <>
      <Screens />
      <Address />
    </>,
  )
  const rows = await listing('Processes')
  fireEvent.change(rows.getByLabelText('Filter the processes'), { target: { value: 'proc' } })
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('q=proc'))
  expect(screen.getByTestId('address').textContent).not.toContain('cursor')
  await waitFor(() => expect(readSearchProcesses.mock.calls.at(-1)?.[1]).toMatchObject({ query: 'proc' }))
  expect(readSearchProcesses.mock.calls.at(-1)?.[1].cursor).toBeUndefined()
  fireEvent.change(screen.getByLabelText('Unit'), { target: { value: 'kilogram' } })
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('unit=kilogram'))
})

it('says location and unit are filters when a process search finds nothing', async () => {
  readSearchProcesses.mockResolvedValue({
    ...processesPage,
    items: [],
    has_more: false,
    next_cursor: null,
    hint: 'no matches with location, unit applied; the words alone match: drop a filter',
  })
  renderAt('/databases/fixture/search/processes?q=electricity%20Chile', <Screens />)
  expect(await screen.findByText('No match.')).toBeInTheDocument()
  expect(await screen.findByText(/no matches with location, unit applied/)).toBeInTheDocument()
})

it('says the compartment is a filter when an elementary flow search finds nothing', async () => {
  readSearchFlows.mockResolvedValue({
    ...flowsPage,
    items: [],
    has_more: false,
    next_cursor: null,
    hint: 'no matches with compartment applied; the words alone match: drop a filter',
  })
  renderAt('/databases/fixture/search/elementary-flows?q=copper%20in%20water', <Screens />)
  expect(await screen.findByText('No match.')).toBeInTheDocument()
  expect(await screen.findByText(/no matches with compartment applied/)).toBeInTheDocument()
})

it('keeps a long filter from widening the panel', async () => {
  renderAt('/databases/fixture/search/processes', <Screens />)
  expect(await screen.findByLabelText('Location')).toHaveClass('max-w-full')
  expect(screen.getByLabelText('Filter the processes')).toHaveClass('min-w-0')
})

it('pages a method search with More, as the other searches page', async () => {
  renderAt('/databases/fixture/search/methods?q=climate', <Screens />)
  const rows = await listing('Indicators')
  await waitFor(() => expect(rows.getByText('climate change')).toBeInTheDocument())
  fireEvent.click(await rows.findByRole('button', { name: 'More…' }))
  await waitFor(() => expect(readSearchMethods.mock.calls.at(-1)?.[1].cursor).toBe('m-cursor-1'))
})

it("shows its pager, not the tool's cursor hint, when a search has more", async () => {
  readSearchProcesses.mockResolvedValue({ ...processesPage, hint: "more results; call again with cursor='proc-cursor-1'" })
  renderAt('/databases/fixture/search/processes?q=hinted', <Screens />)
  const rows = await listing('Processes')
  await waitFor(() => expect(rows.getByRole('button', { name: 'More…' })).toBeInTheDocument())
  expect(screen.queryByText(/call again with cursor/)).not.toBeInTheDocument()
})

it('offers only the compartments a flow search filters by, not their sub-compartments', async () => {
  renderAt('/databases/fixture/search/elementary-flows', <Screens />)
  const select = await screen.findByLabelText('Compartment')
  await waitFor(() => expect(within(select).getByRole('option', { name: 'air' })).toBeInTheDocument())
  const options = within(select).getAllByRole('option').map((option) => option.textContent)
  expect(options).toContain('Resource')
  expect(options).not.toContain('air/urban air close to ground')
  expect(options).not.toContain('Resource/in water')
})

it('names the whole-database search over the processes while the switch is on, and the node again when it is off', async () => {
  renderAt('/databases/fixture/datasets?node=24', <Screens />)
  const rows = await listing('Processes')
  await waitFor(() => expect(rows.getByRole('heading').textContent).toContain('Manufacture of basic metals'))
  expect(rows.getByRole('heading').textContent).toContain('3')
  fireEvent.click(rows.getByLabelText('Search the whole database'))
  await waitFor(() => expect(rows.getByRole('heading').textContent).toBe('Whole-database search'))
  fireEvent.click(rows.getByLabelText('Search the whole database'))
  await waitFor(() => expect(rows.getByRole('heading').textContent).toContain('Manufacture of basic metals'))
  expect(rows.getByRole('heading').textContent).toContain('3')
})

it('names the whole-database search over the flows while the switch is on, and the compartment again when it is off', async () => {
  renderAt('/databases/fixture/flows?compartment=air', <Screens />)
  const rows = await listing('Elementary flows')
  await waitFor(() => expect(rows.getByRole('heading').textContent).toContain('air'))
  expect(rows.getByRole('heading').textContent).toContain('3')
  fireEvent.click(rows.getByLabelText('Search the whole database'))
  await waitFor(() => expect(rows.getByRole('heading').textContent).toBe('Whole-database search'))
  fireEvent.click(rows.getByLabelText('Search the whole database'))
  await waitFor(() => expect(rows.getByRole('heading').textContent).toContain('air'))
  expect(rows.getByRole('heading').textContent).toContain('3')
})
