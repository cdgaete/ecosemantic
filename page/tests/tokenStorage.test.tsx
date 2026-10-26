import { Route, Routes } from 'react-router-dom'
import { waitFor } from '@testing-library/react'
import { ResultsEditor } from '@/editors/results/ResultsEditor'
import { rememberToken } from '@/api/client'
import { useUi } from '@/store/ui'
import { renderAt } from './render'
import impact from './fixtures/impact.json'
import system from './fixtures/system.json'
import validation from './fixtures/validation.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: { ...original.api, system: vi.fn(async () => system), validation: vi.fn(async () => validation), impact: vi.fn(async () => impact) },
  }
})

it('stores no token in the tabs it persists', async () => {
  useUi.setState({ pinned: [], details: null })
  rememberToken('?token=secret')
  const search = `?impact_method=${encodeURIComponent(impact.value.scores[0].method.impact_method)}&token=secret`
  renderAt(
    `/systems/${system.value.id}/results/impact${search}`,
    <Routes>
      <Route path="systems/:id/results/*" element={<ResultsEditor />} />
    </Routes>,
  )
  await waitFor(() => expect(useUi.getState().details?.id).toBe(`results:${system.value.id}`))
  useUi.getState().pin()
  expect(useUi.getState().pinned[0].path).toContain('impact_method=')
  expect(localStorage.getItem('ecosemantic-page')).not.toContain('secret')
})
