import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { Screens } from '@/App'
import type {
  Answer,
  Compartment,
  DatabaseSummary,
  ElementaryFlow,
  ElementaryFlowHit,
  Factor,
  Listing,
  Method,
  MethodFamily,
  Page,
  Term,
  VocabularyKind,
} from '@/api/types'
import explorerSummary from './fixtures/explorer_summary.json'
import explorerCompartments from './fixtures/explorer_compartments.json'
import explorerFlows from './fixtures/explorer_flows.json'
import explorerMethods from './fixtures/explorer_methods.json'
import explorerFactors from './fixtures/explorer_factors.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import searchElementaryFlows from './fixtures/search_elementary_flows.json'
import searchMethods from './fixtures/search_methods.json'
import { renderAt } from './render'

const summary = explorerSummary as Answer<DatabaseSummary>
const compartments = explorerCompartments as Answer<Compartment[]>
const flows = explorerFlows as Answer<Page<ElementaryFlowHit>>
const families = explorerMethods as Answer<MethodFamily[]>
const factors = explorerFactors as Answer<Page<Factor>>
const river = elementaryFlow as Answer<ElementaryFlow>
const flowHits = searchElementaryFlows as unknown as Listing<ElementaryFlowHit>
const methodHits = searchMethods as unknown as Listing<Method>
const units: Answer<Term[]> = {
  hint: null,
  value: [
    { value: 'cubic meter', detail: null },
    { value: 'kilogram', detail: null },
    { value: 'unit', detail: null },
  ],
  view_url: null,
}
const locations: Answer<Term[]> = { hint: null, value: [{ value: 'GLO', detail: 'Global' }], view_url: null }

const RIVER = river.value.ref.id
const CARBON = '7033761e-a295-5042-bedc-164a1623396b'
const METHANE = '0c722450-3926-581f-8be4-c0360f458cde'
const GWP100 = 'm_bff077f3bd'

interface FlowsParams {
  sub_compartment?: string
  query?: string
  limit?: number
  cursor?: string
}

interface FactorsParams {
  query?: string
  limit?: number
  cursor?: string
}

interface SearchParams {
  query: string
  compartment?: string
  limit?: number
  cursor?: string
}

type SummaryRead = (database: string) => Promise<Answer<DatabaseSummary>>
type CompartmentsRead = (database: string) => Promise<Answer<Compartment[]>>
type FlowsRead = (database: string, compartment: string, params: FlowsParams) => Promise<Answer<Page<ElementaryFlowHit>>>
type MethodsRead = (database: string) => Promise<Answer<MethodFamily[]>>
type FactorsRead = (database: string, id: string, params: FactorsParams) => Promise<Answer<Page<Factor>>>
type VocabularyRead = (database: string, kind: VocabularyKind) => Promise<Answer<Term[]>>
type FlowSearchRead = (database: string, params: SearchParams) => Promise<Listing<ElementaryFlowHit>>
type MethodSearchRead = (database: string, params: SearchParams) => Promise<Listing<Method>>
type FlowRead = (database: string, id: string) => Promise<Answer<ElementaryFlow>>

const readSummary = vi.fn<SummaryRead>(async () => summary)
const readCompartments = vi.fn<CompartmentsRead>(async () => compartments)
const readFlowsIn = vi.fn<FlowsRead>(async () => flows)
const readMethodTree = vi.fn<MethodsRead>(async () => families)
const readFlow = vi.fn<FlowRead>(async () => river)
const readVocabulary = vi.fn<VocabularyRead>(async (_database, kind) => (kind === 'units' ? units : locations))
const readSearchFlows = vi.fn<FlowSearchRead>(async () => flowHits)
const readSearchMethods = vi.fn<MethodSearchRead>(async () => methodHits)
const readFactors = vi.fn<FactorsRead>(async (_database, _id, params) => {
  const term = (params.query ?? '').toLocaleLowerCase()
  return { ...factors, value: { ...factors.value, items: factors.value.items.filter((item) => item.name.toLocaleLowerCase().includes(term)) } }
})

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      summary: (database: string) => readSummary(database),
      compartments: (database: string) => readCompartments(database),
      flowsIn: (database: string, compartment: string, params: FlowsParams) => readFlowsIn(database, compartment, params),
      methodTree: (database: string) => readMethodTree(database),
      factors: (database: string, id: string, params: FactorsParams) => readFactors(database, id, params),
      elementaryFlow: (database: string, id: string) => readFlow(database, id),
      vocabulary: (database: string, kind: VocabularyKind) => readVocabulary(database, kind),
      searchElementaryFlows: (database: string, params: SearchParams) => readSearchFlows(database, params),
      searchMethods: (database: string, params: SearchParams) => readSearchMethods(database, params),
    },
  }
})

function Address() {
  const location = useLocation()
  return <output data-testid="address">{location.search}</output>
}

const tree = async (name: string) => within(await screen.findByRole('navigation', { name }))
const listing = async (name: string) => within(await screen.findByRole('region', { name }))
const detail = async (name: string) => within(await screen.findByRole('region', { name }))

beforeEach(() => {
  readSummary.mockReset().mockResolvedValue(summary)
  readCompartments.mockReset().mockResolvedValue(compartments)
  readFlowsIn.mockReset().mockResolvedValue(flows)
  readMethodTree.mockReset().mockResolvedValue(families)
  readFlow.mockReset().mockResolvedValue(river)
  readVocabulary.mockReset().mockImplementation(async (_database, kind) => (kind === 'units' ? units : locations))
  readSearchFlows.mockReset().mockResolvedValue(flowHits)
  readSearchMethods.mockReset().mockResolvedValue(methodHits)
  readFactors.mockReset().mockImplementation(async (_database, _id, params) => {
    const term = (params.query ?? '').toLocaleLowerCase()
    return { ...factors, value: { ...factors.value, items: factors.value.items.filter((item) => item.name.toLocaleLowerCase().includes(term)) } }
  })
})

it('walks air to urban air close to ground and lists Particulate matter', async () => {
  renderAt('/databases/fixture/flows', <Screens />)
  const nodes = await tree('Compartments')
  fireEvent.click(await nodes.findByRole('button', { name: /^air/ }))
  await waitFor(() => expect(readFlowsIn.mock.calls.at(-1)?.[1]).toBe('air'))
  const opened = await listing('Elementary flows')
  expect(await opened.findByText('Particulate matter')).toBeInTheDocument()
  expect(opened.getByText('3')).toBeInTheDocument()
  fireEvent.click(await nodes.findByRole('button', { name: /^urban air close to ground/ }))
  await waitFor(() => expect(readFlowsIn.mock.calls.at(-1)?.[2].sub_compartment).toBe('urban air close to ground'))
  const rows = await listing('Elementary flows')
  expect(await rows.findByText('Particulate matter')).toBeInTheDocument()
  expect(rows.getByText('1')).toBeInTheDocument()
  expect(rows.getByText('kilogram')).toBeInTheDocument()
})

it('opens a flow with its CAS number, unit and side', async () => {
  renderAt(`/databases/fixture/flows/${RIVER}`, <Screens />)
  const shown = await detail('Water, river')
  expect(shown.getByText('cubic meter')).toBeInTheDocument()
  expect(shown.getByText('input')).toBeInTheDocument()
  expect(shown.getByText('Resource')).toBeInTheDocument()
  expect(shown.getByText('in water')).toBeInTheDocument()
  const cas = shown.getByText('CAS number').closest('div')
  expect(cas?.lastElementChild).toBeEmptyDOMElement()
})

it('walks gwp to climate change and opens GWP100 with its two factors', async () => {
  renderAt('/databases/fixture/methods', <Screens />)
  const nodes = await tree('Impact methods')
  fireEvent.click(await nodes.findByRole('button', { name: /^gwp/ }))
  fireEvent.click(await nodes.findByRole('button', { name: /^climate change/ }))
  const rows = await listing('Indicators')
  fireEvent.click(await rows.findByRole('link', { name: 'GWP100' }))
  await waitFor(() => expect(readFactors.mock.calls.at(-1)?.[1]).toBe(GWP100))
  const shown = await detail('GWP100')
  expect(await shown.findByRole('link', { name: 'Carbon dioxide, fossil' })).toHaveAttribute('href', `/databases/fixture/flows/${CARBON}`)
  expect(shown.getByRole('link', { name: 'Methane, fossil' })).toHaveAttribute('href', `/databases/fixture/flows/${METHANE}`)
  expect(shown.getByText('1')).toBeInTheDocument()
  expect(shown.getByText('28')).toBeInTheDocument()
})

it('filters the factors to methane', async () => {
  renderAt(`/databases/fixture/methods/${GWP100}`, <Screens />)
  const shown = await detail('GWP100')
  expect(await shown.findByText('Carbon dioxide, fossil')).toBeInTheDocument()
  fireEvent.change(shown.getByLabelText('Filter the factors'), { target: { value: 'methane' } })
  await waitFor(() => expect(readFactors.mock.calls.at(-1)?.[2].query).toBe('methane'))
  await waitFor(() => expect(shown.queryByText('Carbon dioxide, fossil')).toBeNull())
  expect(shown.getByText('Methane, fossil')).toBeInTheDocument()
})

it('widens the detail over the table and gives the space back', async () => {
  renderAt(
    `/databases/fixture/flows/${RIVER}`,
    <>
      <Screens />
      <Address />
    </>,
  )
  expect(await screen.findByRole('region', { name: 'Elementary flows' })).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: "Take the table's space" }))
  await waitFor(() => expect(screen.getByTestId('address')).toHaveTextContent('wide=1'))
  expect(screen.queryByRole('region', { name: 'Elementary flows' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Give the space back' }))
  await waitFor(() => expect(screen.getByTestId('address')).not.toHaveTextContent('wide=1'))
  expect(await screen.findByRole('region', { name: 'Elementary flows' })).toBeInTheDocument()
})

it('lists the units and the locations', async () => {
  const first = renderAt('/databases/fixture/units', <Screens />)
  const unitsList = await listing('Units')
  expect(await unitsList.findByText('kilogram')).toBeInTheDocument()
  expect(unitsList.getByText('3')).toBeInTheDocument()
  fireEvent.change(unitsList.getByLabelText('Filter the units'), { target: { value: 'kilo' } })
  await waitFor(() => expect(unitsList.queryByText('cubic meter')).toBeNull())
  expect(unitsList.getByText('kilogram')).toBeInTheDocument()
  expect(unitsList.getByText('3')).toBeInTheDocument()
  first.unmount()
  renderAt('/databases/fixture/locations', <Screens />)
  const locationsList = await listing('Locations')
  expect(await locationsList.findByText('GLO')).toBeInTheDocument()
  expect(locationsList.getByText('1')).toBeInTheDocument()
})
