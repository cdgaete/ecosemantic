import { fireEvent, screen, waitFor } from '@testing-library/react'
import { api } from '@/api/client'
import { useUi } from '@/store/ui'
import { useFiles } from '@/window/files'
import { renderAt } from './render'

vi.mock('@/api/queries', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/queries')>()
  return { ...original, useSystem: () => ({ data: undefined }) }
})

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, resultZip: vi.fn() } }
})

const clicked: HTMLAnchorElement[] = []

function Download() {
  const files = useFiles()
  return (
    <button type="button" onClick={() => files.downloadResult('impact')}>
      Download
    </button>
  )
}

describe('the file a download saves', () => {
  beforeEach(() => {
    useUi.setState({ canvasSystemId: 's1' })
    clicked.length = 0
    URL.createObjectURL = vi.fn(() => 'blob:s1')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this)
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('saves a result under the name the server gives', async () => {
    vi.mocked(api.resultZip).mockResolvedValue({ blob: new Blob(['zip']), name: 'widget-aa32c4d5-impact.zip' })
    renderAt('/systems/s1/results/impact?method_id=m1', <Download />)
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))
    await waitFor(() => expect(clicked[0]?.download).toBe('widget-aa32c4d5-impact.zip'))
  })
})
