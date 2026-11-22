import { screen, waitFor, within } from '@testing-library/react'
import { App } from '@/App'
import { api } from '@/api/client'
import type { Answer, ContributionResult, StageInput, StagePart, StageProcess } from '@/api/types'
import { formatAmount } from '@/lib/format'
import databases from './fixtures/databases.json'
import impact from './fixtures/impact.json'
import recorded from './fixtures/contributions_stage.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import validation from './fixtures/validation.json'
import { renderAt } from './render'

const base = recorded as unknown as Answer<ContributionResult>

function splitOf(stages: StagePart[], total: number): Answer<ContributionResult> {
  return {
    ...base,
    value: {
      ...base.value,
      by: 'stage',
      total: { ...base.value.total, value: total },
      stages,
    },
  }
}

function input(name: string, score: number, total: number): StageInput {
  return {
    kind: 'process',
    ref: { kind: 'background', database: 'fixture', id: `fixture-${name}` },
    name,
    location: 'GLO',
    score,
    fraction: score / total,
  }
}

function process(name: string, code: string, score: number, direct: number, inputs: StageInput[], total: number): StageProcess {
  return {
    ref: { kind: 'foreground', code },
    name,
    location: 'GLO',
    score,
    fraction: score / total,
    direct,
    inputs,
  }
}

const TOTAL = 4.158
const WIDGET = process('widget', 'widget', 2.49, 0.1, [input('steel', 1.39, TOTAL), input('electricity', 1, TOTAL)], TOTAL)
const FRAME = process('frame', 'frame', 1.668, 0, [input('steel', 1.668, TOTAL)], TOTAL)
const SPLIT: StagePart[] = [
  { stage: 'assembly', score: 2.49, fraction: 2.49 / TOTAL, processes: [WIDGET] },
  { stage: 'materials', score: 1.668, fraction: 1.668 / TOTAL, processes: [FRAME] },
]

const id = system.value.id
const method = impact.value.methods[0].impact_method
// App holds one query client for the whole file, so each address carries an amount of its own
// and no page reads an answer a test before it asked for.
const at = (amount: number) => `/systems/${id}/results/stages?impact_method=${encodeURIComponent(method)}&amount=${amount}`

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
      contributions: vi.fn(async () => base),
    },
  }
})

it('each stage is listed in the split’s order with its share and score', async () => {
  vi.mocked(api.contributions).mockResolvedValue(splitOf(SPLIT, TOTAL))
  renderAt(at(2), <App router={false} />)
  const table = await waitFor(() => screen.getByRole('table'))
  await waitFor(() => expect(within(table).getByText('assembly')).toBeInTheDocument())
  const rows = within(table).getAllByRole('row').map((row) => row.textContent ?? '')
  const assembly = rows.findIndex((text) => text.includes('assembly'))
  const materials = rows.findIndex((text) => text.includes('materials'))
  expect(assembly).toBeGreaterThan(0)
  expect(assembly).toBeLessThan(materials)
  expect(rows[assembly]).toContain('59.9 %')
  expect(rows[assembly]).toContain(formatAmount(2.49))
  expect(rows[materials]).toContain('40.1 %')
  expect(rows[materials]).toContain(formatAmount(1.668))
  const widget = rows.findIndex((text) => text.includes('widget'))
  expect(widget).toBeGreaterThan(assembly)
  expect(widget).toBeLessThan(materials)
  expect(rows[widget]).toContain(formatAmount(2.49))
  for (const name of ['direct', 'steel', 'electricity']) {
    const held = rows.findIndex((text) => text.includes(name))
    expect(held).toBeGreaterThan(widget)
    expect(held).toBeLessThan(materials)
  }
})

it('a negative share is printed with its sign', async () => {
  const short: StagePart[] = [
    { stage: 'assembly', score: -0.01, fraction: -0.01 / 1.658, processes: [process('widget', 'widget', -0.01, -0.01, [], 1.658)] },
  ]
  vi.mocked(api.contributions).mockResolvedValue(splitOf(short, 1.658))
  renderAt(at(3), <App router={false} />)
  const table = await waitFor(() => screen.getByRole('table'))
  await waitFor(() => expect(within(table).getByText('assembly')).toBeInTheDocument())
  const rows = within(table).getAllByRole('row').map((row) => row.textContent ?? '')
  expect(rows[1]).toContain('assembly')
  expect(rows[1]).toContain('-0.6 %')
  const paints = [...table.querySelectorAll('span[style]')].map((span) => span.getAttribute('style') ?? '')
  expect(paints.some((style) => style.includes('rgb(var(--stage-1) / 1)'))).toBe(true)
})

it('a system without stages reads one part of no stage', async () => {
  vi.mocked(api.contributions).mockResolvedValue(splitOf([{ stage: null, score: TOTAL, fraction: 1, processes: [WIDGET, FRAME] }], TOTAL))
  renderAt(at(4), <App router={false} />)
  const table = await waitFor(() => screen.getByRole('table'))
  await waitFor(() => expect(within(table).getByText('no stage')).toBeInTheDocument())
  expect(within(table).getAllByText('no stage')).toHaveLength(1)
})

it('the split is read under the case and the category', async () => {
  vi.mocked(api.contributions).mockResolvedValue(splitOf(SPLIT, TOTAL))
  renderAt(`${at(5)}&variant=heavy`, <App router={false} />)
  await waitFor(() =>
    expect(api.contributions).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ by: 'stage', method_id: 'm_bff077f3bd', variant: 'heavy' })),
  )
})
