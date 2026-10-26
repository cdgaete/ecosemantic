import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { ApiError, api } from '@/api/client'
import type { LogEntry } from '@/api/types'
import { useUi } from '@/store/ui'
import { ImportDialog } from '@/window/ImportDialog'
import log from './fixtures/log.json'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, returnTables: vi.fn(), returnPackage: vi.fn() } }
})

const zip = new File(['zip'], 'tables.zip', { type: 'application/zip' })
const entry = log.value[0] as LogEntry

function choose(): void {
  fireEvent.change(screen.getByLabelText('File'), { target: { files: [zip] } })
  fireEvent.click(screen.getByRole('button', { name: 'Import' }))
}

describe('import dialog', () => {
  beforeEach(() => {
    useUi.setState({ person: 'Carlos' })
  })

  it('posts the tables under the person and says which entry they became', async () => {
    vi.mocked(api.returnTables).mockResolvedValue(entry)
    renderAt('/', <ImportDialog systemId="s1" format="tables" onClose={() => undefined} />)
    expect(screen.getByText('Import tables')).toBeInTheDocument()
    choose()
    await waitFor(() => expect(screen.getByText(`Imported as entry #${entry.seq}`)).toBeInTheDocument())
    expect(api.returnTables).toHaveBeenCalledWith('s1', zip, 'Carlos')
  })

  it('posts an openLCA package through the return', async () => {
    vi.mocked(api.returnPackage).mockResolvedValue(entry)
    renderAt('/', <ImportDialog systemId="s1" format="openlca" onClose={() => undefined} />)
    expect(screen.getByText('Import an openLCA package')).toBeInTheDocument()
    choose()
    await waitFor(() => expect(api.returnPackage).toHaveBeenCalledWith('s1', zip, 'Carlos', ''))
  })

  it('posts an openLCA package with the entry the person says it was exported at', async () => {
    vi.mocked(api.returnPackage).mockResolvedValue(entry)
    renderAt('/', <ImportDialog systemId="s1" format="openlca" onClose={() => undefined} />)
    fireEvent.change(screen.getByLabelText('Exported at entry (optional)'), { target: { value: '12' } })
    choose()
    await waitFor(() => expect(api.returnPackage).toHaveBeenCalledWith('s1', zip, 'Carlos', '12'))
  })

  it('asks for the exported entry on an openLCA package alone', () => {
    renderAt('/', <ImportDialog systemId="s1" format="tables" onClose={() => undefined} />)
    expect(screen.queryByLabelText('Exported at entry (optional)')).toBeNull()
  })

  it('draws a refusal cell by cell', async () => {
    const refusals = [{ file: 'inputs/input_parameters.csv', row: 3, column: 'value', found: 'abc', reason: 'not a number' }]
    vi.mocked(api.returnTables).mockRejectedValue(new ApiError(400, { error: 'invalid', message: '1 cell cannot be read', details: { refusals } }))
    renderAt('/', <ImportDialog systemId="s1" format="tables" onClose={() => undefined} />)
    choose()
    await waitFor(() => expect(screen.getByText('1 cell cannot be read')).toBeInTheDocument())
    expect(screen.getByText('inputs/input_parameters.csv')).toBeInTheDocument()
    expect(screen.getByText('not a number')).toBeInTheDocument()
  })

  it('asks for a name when the browser holds none', () => {
    useUi.setState({ person: null })
    renderAt('/', <ImportDialog systemId="s1" format="tables" onClose={() => undefined} />)
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
    expect(screen.getByLabelText('Your name')).toBeInTheDocument()
  })
})
