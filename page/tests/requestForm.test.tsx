import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderAt } from './render'
import { RequestForm } from '@/requests/RequestForm'
import { useUi } from '@/store/ui'

const posted = vi.fn(async (_id: string, draft: unknown) => ({ ...(draft as object), id: 'r1', seq: 1, open: true }))
vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, postRequest: (id: string, draft: unknown) => posted(id, draft) } }
})

describe('request form', () => {
  it('asks the name once, names the entity it was opened from, and posts at the hash on screen', async () => {
    useUi.setState({ person: null })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" entity="process" entityId="tshirt" onDone={() => {}} />)
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Carlos' } })
    expect(screen.getByLabelText('Kind')).toHaveValue('edit')
    expect(screen.getByText('process · tshirt')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'use the organic yarn' } })
    fireEvent.click(screen.getByText('Post request'))
    await waitFor(() => expect(posted).toHaveBeenCalled())
    expect(posted.mock.calls[0][1]).toEqual({ actor: 'Carlos', kind: 'edit', at_hash: 'h1', message: 'use the organic yarn', entity: 'process', entity_id: 'tshirt' })
    expect(useUi.getState().person).toBe('Carlos')
  })

  it('offers approve and return without an entity', () => {
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" onDone={() => {}} />)
    expect(screen.queryByLabelText('Your name')).toBeNull()
    expect(screen.getByLabelText('Kind')).toHaveValue('return')
  })

  it('posts a return with no entity fields when the section names an entity without an id', async () => {
    posted.mockClear()
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" entity="parameter" onDone={() => {}} />)
    expect(screen.getByLabelText('Kind')).toHaveValue('return')
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'the transport distance looks high' } })
    fireEvent.click(screen.getByText('Post request'))
    await waitFor(() => expect(posted).toHaveBeenCalled())
    expect(posted.mock.calls[0][1]).toEqual({ actor: 'Carlos', kind: 'return', at_hash: 'h1', message: 'the transport distance looks high' })
  })
})
