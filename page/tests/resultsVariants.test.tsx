import { screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { App } from '@/App'
import { formatAmount } from '@/lib/format'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import databases from './fixtures/databases.json'
import validation from './fixtures/validation.json'
import impact from './fixtures/impact.json'

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
    },
  }
})

it('keeps the score on screen in a narrow panel: the category folds away and the variants go under the name', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}&variants=small`, <App router={false} />)
  const header = await screen.findByRole('columnheader', { name: 'Category' })
  expect(header).toHaveClass('hidden', '@lg:table-cell')
  const variant = withVariant.value.variants[0]
  const sign = variant.deltas[0] >= 0 ? '+' : '−'
  const line = await screen.findByText(`small: ${formatAmount(variant.scores[0].value)} (${sign}${formatAmount(Math.abs(variant.deltas[0]))})`)
  expect(line).toHaveClass('@lg:hidden')
  expect(line.closest('td')?.className).not.toContain('whitespace-nowrap')
})

it('shows one column per variant with its score and delta', async () => {
  renderAt(`/systems/${system.value.id}/results/impact?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}&variants=small`, <App router={false} />)
  await waitFor(() => expect(screen.getByText('small (Δ)')).toBeInTheDocument())
  const variant = withVariant.value.variants[0]
  const half = formatAmount(variant.scores[0].value)
  const sign = variant.deltas[0] >= 0 ? '+' : '−'
  const cell = `${half} (${sign}${formatAmount(Math.abs(variant.deltas[0]))})`
  await waitFor(() => expect(screen.getByText(cell)).toBeInTheDocument())
})
