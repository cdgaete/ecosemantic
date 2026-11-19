import { screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import type { Answer, BackgroundProcess } from '@/api/types'
import { DatasetPeek } from '@/editors/explorer/DatasetPeek'
import { useUi } from '@/store/ui'
import backgroundProcess from './fixtures/background_process.json'
import elementaryFlow from './fixtures/elementary_flow.json'
import system from './fixtures/system.json'
import { renderAt } from './render'

const process = backgroundProcess as Answer<BackgroundProcess>

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      backgroundProcess: vi.fn(async () => process),
      elementaryFlows: vi.fn(async (_database: string, ids: string[]) => ({ ...elementaryFlow, value: ids.map((id) => ({ ...elementaryFlow.value, ref: { ...elementaryFlow.value.ref, id } })) })),
    },
  }
})

const id = system.value.id
const ref = process.value.ref.id
const supplier = process.value.exchanges?.find((exchange) => exchange.supplier !== null)
const address = `/systems/${id}/datasets/fixture/${ref}`

function renderPeek() {
  return renderAt(
    address,
    <Routes>
      <Route path="/systems/:id/datasets/:database/*" element={<DatasetPeek />} />
    </Routes>,
  )
}

beforeEach(() => {
  useUi.setState({ details: null, lastDetails: null, pinned: [] })
})

it('shows a dataset beside the graph, with a link to it in the explorer', async () => {
  renderPeek()
  expect(await screen.findByRole('heading', { name: `Dataset – ${process.value.name}` })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open in the explorer' })).toHaveAttribute('href', `/databases/fixture/processes/${ref}`)
  const shown = within(await screen.findByRole('region', { name: process.value.name }))
  expect(shown.getByText('Reference product').nextElementSibling).toHaveTextContent(process.value.reference_product)
  expect(shown.getByText('Inputs')).toBeInTheDocument()
})

it('has no listing to return to and no table to take the space of', async () => {
  renderPeek()
  await screen.findByRole('region', { name: process.value.name })
  expect(screen.queryByRole('button', { name: 'Show the listing' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: "Take the table's space" })).not.toBeInTheDocument()
})

it('keeps a supplier of the dataset beside the graph, and sends a flow and a classification to the explorer', async () => {
  renderPeek()
  const shown = within(await screen.findByRole('region', { name: process.value.name }))
  const provider = await shown.findByRole('link', { name: new RegExp(supplier?.supplier ?? 'no supplier') })
  expect(provider).toHaveAttribute('href', `/systems/${id}/datasets/fixture/${supplier?.input?.kind === 'background' ? supplier.input.id : ''}`)
  expect(shown.getByText('Carbon dioxide, fossil').closest('a')?.getAttribute('href')).toMatch(/^\/databases\/fixture\/flows\//)
  const classified = shown.getByText('ISIC rev.4 ecoinvent').closest('tr') as HTMLElement
  expect(within(classified).getByRole('link').getAttribute('href')).toMatch(/^\/databases\/fixture\/datasets\?/)
})

it('is what Details holds, under the name of the dataset', async () => {
  renderPeek()
  await screen.findByRole('region', { name: process.value.name })
  await waitFor(() => expect(useUi.getState().details).toEqual({ id: `dataset:fixture:${ref}`, kind: 'explorer', title: `Dataset: ${process.value.name}`, path: address }))
})
