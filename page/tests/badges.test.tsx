import { screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { api, ApiError } from '@/api/client'
import { ValidationBadge } from '@/window/Badges'
import validationErrors from './fixtures/validation_errors.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, validation: vi.fn(async () => validationErrors) } }
})

describe('validation badge', () => {
  it('counts the issue of a system that names no reference process', async () => {
    renderAt('/', <ValidationBadge id="unfinished" />)
    await waitFor(() => expect(screen.getByRole('link', { name: '⚠ 1 issue' })).toBeInTheDocument())
  })

  it('says a system is not validated when validation fails, with the reason as its title', async () => {
    vi.mocked(api.validation).mockRejectedValueOnce(new ApiError(404, { error: 'not_found', message: 'no product_system gone', details: {} }))
    renderAt('/', <ValidationBadge id="gone" />)
    const badge = await screen.findByRole('link', { name: '⚠ Not validated' })
    expect(badge).toHaveAttribute('title', 'no product_system gone')
  })
})
