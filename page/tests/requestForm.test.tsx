import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './render'
import { RequestDialog } from '@/requests/RequestDialog'
import { RequestForm } from '@/requests/RequestForm'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import type { ProductSystem } from '@/api/types'
import system from './fixtures/system.json'

const posted = vi.fn(async (_id: string, draft: unknown) => ({ ...(draft as object), id: 'r1', seq: 1, open: true }))
vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return { ...original, api: { ...original.api, postRequest: (id: string, draft: unknown) => posted(id, draft), system: vi.fn(async () => system) } }
})

const doc = system.value as ProductSystem
const frame = doc.processes.find((p) => p.code === 'frame')!
const FRAME_EXCHANGE = doc.processes.find((p) => p.code === 'widget')!.exchanges.find((e) => e.name === 'frame')!

describe('request form', () => {
  it('asks the name once, names the entity it was opened from, and posts at the hash on screen', async () => {
    useUi.setState({ person: null })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} entity="process" entityId="frame" onDone={() => {}} />)
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Carlos' } })
    expect(screen.getByLabelText('Kind')).toHaveValue('edit')
    expect(screen.getByTitle('frame')).toHaveTextContent(frame.name)
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'use the organic yarn' } })
    fireEvent.click(screen.getByText('Post request'))
    await waitFor(() => expect(posted).toHaveBeenCalled())
    expect(posted.mock.calls[0][1]).toEqual({ actor: 'Carlos', kind: 'edit', at_hash: 'h1', message: 'use the organic yarn', entity: 'process', entity_id: 'frame' })
    expect(useUi.getState().person).toBe('Carlos')
  })

  it('offers approve and return without an entity', () => {
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} onDone={() => {}} />)
    expect(screen.queryByLabelText('Your name')).toBeNull()
    expect(screen.getByLabelText('Kind')).toHaveValue('return')
  })

  it('posts a return with no entity fields when the section names an entity without an id', async () => {
    posted.mockClear()
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} entity="parameter" onDone={() => {}} />)
    expect(screen.getByLabelText('Kind')).toHaveValue('return')
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'the transport distance looks high' } })
    fireEvent.click(screen.getByText('Post request'))
    await waitFor(() => expect(posted).toHaveBeenCalled())
    expect(posted.mock.calls[0][1]).toEqual({ actor: 'Carlos', kind: 'return', at_hash: 'h1', message: 'the transport distance looks high' })
  })

  it('names each kind by what it does, and says what the chosen one does', () => {
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} onDone={() => {}} />)
    const select = screen.getByLabelText('Kind')
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual(['Return with an objection', 'Approve'])
    expect(screen.getByText('The agent is asked to answer it, and it stays open until it is resolved.')).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'approve' } })
    expect(screen.getByText('Recorded beside the model: never counted, never open.')).toBeInTheDocument()
    expect(
      screen.getByText("An open return or change is counted in the answer to the agent's next write and when it reads the product system."),
    ).toBeInTheDocument()
  })

  it('offers a change to the entity it was opened from, and says the change stays open', () => {
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} entity="process" entityId="frame" onDone={() => {}} />)
    const select = screen.getByLabelText('Kind')
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Ask for a change to process',
      'Return with an objection',
      'Approve',
    ])
    expect(screen.getByText('It stays open until it is resolved.')).toBeInTheDocument()
  })

  it('a request on the product system names it in words', () => {
    useUi.setState({ person: 'Carlos' })
    renderAt('/', <RequestForm systemId="s1" atHash="h1" system={doc} entity="product_system" entityId={doc.id} onDone={() => {}} />)
    expect(within(screen.getByLabelText('Kind')).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Ask for a change to product system',
      'Return with an objection',
      'Approve',
    ])
  })

  it('the dialog names its entity', async () => {
    useUi.setState({ person: 'Carlos' })
    useRequestDialog.setState({ target: { systemId: doc.id, entity: 'process', entityId: 'frame' } })
    renderAt('/', <RequestDialog />)
    expect(await screen.findByTitle('frame')).toHaveTextContent(frame.name)
    act(() => useRequestDialog.setState({ target: { systemId: doc.id, entity: 'exchange', entityId: FRAME_EXCHANGE.id } }))
    const flow = await screen.findByTitle(FRAME_EXCHANGE.id)
    expect(flow).toHaveTextContent(`${FRAME_EXCHANGE.name} on ${doc.processes.find((p) => p.code === 'widget')!.name}`)
    useRequestDialog.setState({ target: null })
  })
})
