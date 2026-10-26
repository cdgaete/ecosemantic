import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import databases from './fixtures/databases.json'
import byPath from './fixtures/contributions_path.json'
import impact from './fixtures/impact.json'
import inventory from './fixtures/inventory.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

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
      vocabulary: vi.fn(async () => ({ value: [], hint: null, view_url: null })),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => byPath),
      inventory: vi.fn(async () => inventory),
    },
  }
})

const url = `/systems/${system.value.id}/results/tree?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`
const search = url.slice(url.indexOf('?'))

it('keeps every impact category select within its container', async () => {
  const pages = [
    ['processes', 'Impact category'],
    ['tree', 'Impact category'],
    ['sankey', 'Impact category:'],
    ['inventory', 'Compartment'],
  ] as const
  for (const [page, label] of pages) {
    renderAt(`/systems/${system.value.id}/results/${page}${search}`, <App router={false} />)
    const select = await screen.findByLabelText(label)
    expect(select).toHaveClass('min-w-0', 'max-w-full')
    expect(select.closest('label')).toHaveClass('min-w-0', 'max-w-full')
    cleanup()
  }
})

it('shows the path tree with a row per node and the total result unit', async () => {
  renderAt(url, <App router={false} />)
  await waitFor(() => expect(screen.getByRole('heading', { name: /Contribution tree/ })).toBeInTheDocument())
  const table = await waitFor(() => screen.getByRole('table'))
  for (const header of ['Contribution', 'Process', 'Total result', 'Unit']) expect(within(table).getByText(header)).toBeInTheDocument()
  await waitFor(() => expect(within(table).getByText(byPath.value.root.name)).toBeInTheDocument())
  for (const child of byPath.value.root.children.filter((c) => c.kind === 'process')) expect(within(table).getByText(new RegExp(child.name))).toBeInTheDocument()
})

it('draws the Sankey vertically with a node table beside it', async () => {
  renderAt(`/systems/${system.value.id}/results/sankey?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  await waitFor(() => expect(screen.getByRole('heading', { name: /Sankey diagram/ })).toBeInTheDocument())
  const figure = await waitFor(() => screen.getByRole('figure', { name: /Sankey diagram/ }))
  expect(figure).toBeInTheDocument()
  const tables = await waitFor(() => screen.getAllByRole('table'))
  const nodeTable = tables[0]
  for (const header of ['Process', 'Upstream total', `Score [${byPath.value.total.unit}]`]) expect(within(nodeTable).getByText(header)).toBeInTheDocument()
  expect(within(nodeTable).getByText(new RegExp(byPath.value.root.name))).toBeInTheDocument()
})

it('associates each Sankey control with its caption', async () => {
  renderAt(`/systems/${system.value.id}/results/sankey?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  await waitFor(() => expect(screen.getByRole('heading', { name: /Sankey diagram/ })).toBeInTheDocument())
  expect(screen.getByLabelText(/Impact category/)).toBe(document.getElementById('sankey-category'))
  expect(screen.getByLabelText(/Min\. contribution share/)).toBe(document.getElementById('sankey-share'))
  expect(screen.getByLabelText(/Max\. number of processes/)).toBe(document.getElementById('sankey-nodes'))
})

it('has the six result pages and no Simulation page', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}`, <App router={false} />)
  await waitFor(() => expect(screen.getByRole('navigation', { name: 'Pages' })).toBeInTheDocument())
  const nav = screen.getByRole('navigation', { name: 'Pages' })
  expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['General information', 'Inventory results', 'Impact analysis', 'Process results', 'Contribution tree', 'Sankey diagram'])
})

it('says whether each branch of the tree is open', async () => {
  renderAt(url, <App router={false} />)
  const table = await waitFor(() => screen.getByRole('table'))
  await waitFor(() => expect(within(table).getByText(byPath.value.root.name)).toBeInTheDocument())
  const root = within(table).getAllByRole('button', { name: 'Expand' })[0]
  expect(root).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(root)
  await waitFor(() => expect(root).toHaveAttribute('aria-expanded', 'false'))
})
