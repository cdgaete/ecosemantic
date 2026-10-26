import { fireEvent, screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { renderAt } from './render'
import { App, Screens } from '@/App'
import { useUi } from '@/store/ui'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import compartments from './fixtures/vocabulary_compartments.json'
import type { ElementaryFlowHit, Listing, Method, ProcessHit } from '@/api/types'

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

const flowsPage: Listing<ElementaryFlowHit> = {
  hint: null,
  has_more: true,
  next_cursor: 'cursor-1',
  items: [
    {
      ref: { kind: 'elementary_flow', database: 'fixture-biosphere', id: 'a1' },
      name: 'Some flow',
      compartment: 'air',
      sub_compartment: null,
      unit: 'kilogram',
      flow_type: 'emission',
      cas_number: null,
    },
  ],
  view_url: null,
}

const processesPage: Listing<ProcessHit> = {
  hint: null,
  has_more: true,
  next_cursor: 'proc-cursor-1',
  items: [
    {
      ref: { kind: 'background', database: 'fixture', id: 'p1' },
      name: 'Some process',
      reference_product: 'Some product',
      location: 'GLO',
      unit: 'kilogram',
      relevance: 1,
    },
  ],
  view_url: null,
}

const methodsPage: Listing<Method> = {
  hint: "more results; call again with cursor='m-cursor-1'",
  has_more: true,
  next_cursor: 'm-cursor-1',
  items: [
    {
      id: 'm_gwp',
      tuple: ['fixture', 'gwp', 'climate change > GWP100'],
      spec: 'fixture > gwp > climate change > GWP100',
      unit: 'kg CO2-Eq',
      impact_method: 'gwp',
      impact_category: 'climate change',
      indicator: 'GWP100',
    },
  ],
  view_url: null,
}

const searchMethods = vi.fn<(database: string, params: { query: string; limit?: number; cursor?: string }) => Promise<Listing<Method>>>(async () => methodsPage)
const searchElementaryFlows = vi.fn<(database: string, params: FlowsParams) => Promise<Listing<ElementaryFlowHit>>>(async () => flowsPage)
const searchProcesses = vi.fn<(database: string, params: ProcessesParams) => Promise<Listing<ProcessHit>>>(async () => processesPage)

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      vocabulary: vi.fn(async () => compartments),
      searchElementaryFlows: (database: string, params: FlowsParams) => searchElementaryFlows(database, params),
      searchProcesses: (database: string, params: ProcessesParams) => searchProcesses(database, params),
      searchMethods: (database: string, params: { query: string; limit?: number; cursor?: string }) => searchMethods(database, params),
    },
  }
})

it('drops the cursor when a filter changes after paging with More', async () => {
  renderAt('/databases/fixture/search/elementary-flows', <App router={false} />)
  const input = await screen.findByPlaceholderText('Search…')
  fireEvent.change(input, { target: { value: 'flow' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.getByText('Some flow')).toBeInTheDocument())

  await waitFor(() => expect(screen.getByText('More…')).toBeInTheDocument())
  fireEvent.click(screen.getByText('More…'))
  await waitFor(() => expect(searchElementaryFlows.mock.calls.at(-1)?.[1].cursor).toBe('cursor-1'))

  fireEvent.change(screen.getByLabelText('Compartment'), { target: { value: 'air' } })
  await waitFor(() => expect(searchElementaryFlows.mock.calls.at(-1)?.[1].compartment).toBe('air'))
  expect(searchElementaryFlows.mock.calls.at(-1)?.[1].cursor).toBeUndefined()
})

it('starts a fresh search, with no cursor, when the search kind is switched', async () => {
  renderAt('/databases/fixture/search/processes', <App router={false} />)
  const firstInput = await screen.findByPlaceholderText('Search…')
  fireEvent.change(firstInput, { target: { value: 'proc' } })
  fireEvent.submit(firstInput.closest('form')!)
  await waitFor(() => expect(screen.getByText('Some process')).toBeInTheDocument())

  await waitFor(() => expect(screen.getByText('More…')).toBeInTheDocument())
  fireEvent.click(screen.getByText('More…'))
  await waitFor(() => expect(searchProcesses.mock.calls.at(-1)?.[1].cursor).toBe('proc-cursor-1'))

  useUi.getState().setNavOpen(true)
  const elementaryFlowsLinks = await screen.findAllByText('Elementary flows')
  const fixtureLink = elementaryFlowsLinks.map((el) => el.closest('a')).find((a) => a?.getAttribute('href')?.includes('/databases/fixture/search/elementary-flows'))!
  fireEvent.click(fixtureLink)
  const secondInput = await screen.findByPlaceholderText('Search…')
  fireEvent.change(secondInput, { target: { value: 'flow' } })
  fireEvent.submit(secondInput.closest('form')!)
  await waitFor(() => expect(searchElementaryFlows).toHaveBeenCalled())
  expect(searchElementaryFlows.mock.calls.at(-1)?.[1].cursor).toBeUndefined()
})

it("shows the tool's hint under a results table that has rows", async () => {
  searchProcesses.mockResolvedValueOnce({ ...processesPage, has_more: false, next_cursor: null, hint: 'Nearest matches by name; add a location to narrow them.' })
  renderAt('/databases/fixture/search/processes', <App router={false} />)
  const input = await screen.findByPlaceholderText('Search…')
  fireEvent.change(input, { target: { value: 'steel' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.getByText('Some process')).toBeInTheDocument())
  expect(screen.getByText('Nearest matches by name; add a location to narrow them.')).toBeInTheDocument()
})

function Address() {
  const location = useLocation()
  return <output data-testid="address">{location.search}</output>
}

it('draws the hits of the search its address names', async () => {
  searchProcesses.mockClear()
  renderAt('/databases/fixture/search/processes?q=steel&location=GLO', <App router={false} />)
  await waitFor(() => expect(screen.getByText('Some process')).toBeInTheDocument())
  expect(searchProcesses.mock.calls.at(-1)?.[1]).toMatchObject({ query: 'steel', location: 'GLO' })
  expect(screen.getByPlaceholderText('Search…')).toHaveValue('steel')
})

it('writes its query and its filters into the address, and drops the page on a new query', async () => {
  renderAt('/databases/fixture/search/processes?q=old&cursor=proc-cursor-1', <><Screens /><Address /></>)
  const input = await screen.findByPlaceholderText('Search…')
  fireEvent.change(input, { target: { value: 'proc' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('q=proc'))
  expect(screen.getByTestId('address').textContent).not.toContain('cursor')
  await waitFor(() => expect(searchProcesses.mock.calls.at(-1)?.[1]).toMatchObject({ query: 'proc' }))
  expect(searchProcesses.mock.calls.at(-1)?.[1].cursor).toBeUndefined()
  fireEvent.change(screen.getByLabelText('Unit'), { target: { value: compartments.value[0].value } })
  await waitFor(() => expect(screen.getByTestId('address').textContent).toContain('unit='))
})

it('says location and unit are filters when a process search finds nothing', async () => {
  searchProcesses.mockResolvedValueOnce({ ...processesPage, items: [], has_more: false, next_cursor: null })
  renderAt('/databases/fixture/search/processes?q=electricity%20Chile', <App router={false} />)
  expect(await screen.findByText('No match.')).toBeInTheDocument()
  expect(await screen.findByText(/Location and unit are filters/)).toBeInTheDocument()
})

it('says the compartment is a filter when an elementary flow search finds nothing', async () => {
  searchElementaryFlows.mockResolvedValueOnce({ ...flowsPage, items: [], has_more: false, next_cursor: null })
  renderAt('/databases/fixture/search/elementary-flows?q=copper%20in%20water', <App router={false} />)
  expect(await screen.findByText('No match.')).toBeInTheDocument()
  expect(await screen.findByText(/Compartment is a filter/)).toBeInTheDocument()
})

it('keeps a long filter from widening the panel', async () => {
  renderAt('/databases/fixture/search/processes', <App router={false} />)
  expect(await screen.findByLabelText('Location')).toHaveClass('max-w-full')
  expect(screen.getByPlaceholderText('Search…')).toHaveClass('min-w-0')
})

it('names the searches a database offers when the address names no search it has', async () => {
  renderAt('/databases/fixture/search/flows', <App router={false} />)
  expect(await screen.findByText(/has no search named “flows”/)).toBeInTheDocument()
  for (const name of ['Processes', 'Elementary flows', 'Impact methods']) expect(screen.getByRole('link', { name })).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: 'Impact method' })).toBeNull()
})

it('pages a method search with More, as the other searches page', async () => {
  renderAt('/databases/fixture/search/methods', <App router={false} />)
  const input = await screen.findByPlaceholderText('Search…')
  fireEvent.change(input, { target: { value: 'climate' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.getByText('climate change')).toBeInTheDocument())
  fireEvent.click(await screen.findByText('More…'))
  await waitFor(() => expect(searchMethods.mock.calls.at(-1)?.[1].cursor).toBe('m-cursor-1'))
})

it("shows its pager, not the tool's cursor hint, when a search has more", async () => {
  searchProcesses.mockResolvedValue({ ...processesPage, hint: "more results; call again with cursor='proc-cursor-1'" })
  renderAt('/databases/fixture/search/processes', <App router={false} />)
  const input = await screen.findByPlaceholderText('Search…')
  fireEvent.change(input, { target: { value: 'hinted' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.getByText('More…')).toBeInTheDocument())
  expect(screen.queryByText(/call again with cursor/)).not.toBeInTheDocument()
  searchProcesses.mockResolvedValue(processesPage)
})
