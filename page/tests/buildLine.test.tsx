import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { renderAt } from './render'
import { resizePage } from './setup'
import { BuildLine } from '@/activity/BuildLine'
import { api } from '@/api/client'
import type { Call, Value } from '@/api/types'
import { useUi } from '@/store/ui'
import system from './fixtures/system.json'
import log from './fixtures/log.json'
import calculations from './fixtures/calculations.json'
import impact from './fixtures/impact.json'
import contributions from './fixtures/contributions_stage.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      system: vi.fn(async () => system),
      log: vi.fn(async () => log),
      calculations: vi.fn(async () => ({ value: [] })),
      impact: vi.fn(async () => impact),
      contributions: vi.fn(async () => contributions),
    },
  }
})

const id = system.value.id
const recorded = calculations.value[0] as unknown as Call
const runAgain = 'Run again: gwp > climate change > GWP100 · base values'

function Place() {
  const location = useLocation()
  return <output data-testid="place">{`${location.pathname}${location.search}`}</output>
}

const line = () => within(screen.getByRole('toolbar', { name: 'Build line' }))
const place = () => screen.getByTestId('place').textContent ?? ''

function open(calls: Call[]) {
  resizePage(700)
  vi.mocked(api.calculations).mockResolvedValue({ value: calls } as Value<Call[]>)
  return renderAt(
    `/systems/${id}`,
    <>
      <BuildLine systemId={id} live toolsOpen={false} onTools={() => undefined} />
      <Place />
    </>,
  )
}

beforeEach(() => {
  useUi.setState({ startedImpact: null })
})

afterEach(() => resizePage(1024))

it('offers Open result in words and the rest in a labelled menu below 768 px', async () => {
  open([recorded])
  expect(await line().findByRole('button', { name: 'Open result' })).toHaveTextContent('Open result')
  fireEvent.keyDown(line().getByRole('button', { name: 'More calculation actions' }), { key: 'Enter' })
  expect(await screen.findByRole('menuitem', { name: 'New calculation…' })).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('menuitem', { name: runAgain }))
  expect(useUi.getState().startedImpact).toBe(id)
  expect(place()).toBe(`/systems/${id}/results/impact?call=${recorded.id}`)
})

it('opens the result below 768 px without starting a run', async () => {
  open([recorded])
  fireEvent.click(await line().findByRole('button', { name: 'Open result' }))
  expect(place()).toBe(`/systems/${id}/results/impact?call=${recorded.id}`)
  expect(useUi.getState().startedImpact).toBeNull()
})

it('offers only a new calculation below 768 px while no call succeeded', async () => {
  open([])
  expect(await line().findByRole('button', { name: 'New calculation…' })).toHaveTextContent('New calculation…')
  expect(line().queryByRole('button', { name: 'Open result' })).toBeNull()
  expect(line().queryByRole('button', { name: 'More calculation actions' })).toBeNull()
})

it('names the repeat on an icon from 768 px', async () => {
  resizePage(1024)
  vi.mocked(api.calculations).mockResolvedValue({ value: [recorded] } as Value<Call[]>)
  renderAt(
    `/systems/${id}`,
    <>
      <BuildLine systemId={id} live toolsOpen={false} onTools={() => undefined} />
      <Place />
    </>,
  )
  await waitFor(() => expect(screen.getByRole('toolbar', { name: 'Build line' })).toBeInTheDocument())
  expect(await line().findByRole('button', { name: runAgain })).toBeInTheDocument()
  expect(line().queryByRole('button', { name: 'Open result' })).toBeNull()
})
