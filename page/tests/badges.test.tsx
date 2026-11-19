import { screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { api, ApiError } from '@/api/client'
import { ValidationBadge, ValidationMark } from '@/window/Badges'
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

describe('validation mark', () => {
  it('marks a system valid when its report names no issue', () => {
    renderAt('/', <ValidationMark id="cup" issues={0} error={null} />)
    expect(screen.getByRole('link', { name: '✓ Valid' })).toHaveAttribute('href', expect.stringContaining('/systems/cup'))
  })

  it('counts the issues a report names', () => {
    renderAt('/', <ValidationMark id="cup" issues={3} error={null} />)
    expect(screen.getByRole('link', { name: '⚠ 3 issues' })).toBeInTheDocument()
  })

  it('says a system is not validated when its row carries the failure, titled with its message', () => {
    renderAt('/', <ValidationMark id="cup" issues={null} error="no database nowhere" />)
    expect(screen.getByRole('link', { name: '⚠ Not validated' })).toHaveAttribute('title', 'no database nowhere')
  })

  it('shows nothing while the report is not read', () => {
    const { container } = renderAt('/', <ValidationMark id="cup" issues={null} error={null} />)
    expect(container.querySelector('a')).toBeNull()
  })
})
