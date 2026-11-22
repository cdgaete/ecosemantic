import { fireEvent, screen, within } from '@testing-library/react'
import type { ListedDatabase, ProductSystem } from '@/api/types'
import { api } from '@/api/client'
import { places } from '@/editors/explorer/sections'
import { paths } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { NavPane } from '@/window/NavPane'
import databases from './fixtures/databases.json'
import system from './fixtures/system.json'
import systems from './fixtures/systems.json'
import { layoutAnswer } from './placements'
import { renderAt } from './render'

vi.mock('@/api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/client')>()
  return {
    ...original,
    api: {
      ...original.api,
      systems: vi.fn(async () => systems),
      databases: vi.fn(async () => databases),
      system: vi.fn(async () => system),
      layout: vi.fn(async () => layoutAnswer({ stages: [], shared_suppliers: [] })),
    },
  }
})

const listed = databases.value as unknown as ListedDatabase[]
function counted(name: string): ListedDatabase {
  const found = listed.find((database) => database.name === name)
  if (found === undefined) throw new Error(`the fixture lists no ${name}`)
  return found
}

async function rowOf(name: string): Promise<HTMLElement> {
  const link = await screen.findByRole('link', { name: new RegExp(`^${name}`) })
  if (link.parentElement === null) throw new Error(`the row of ${name} holds no element`)
  return link.parentElement
}

async function openSystem(name: string): Promise<void> {
  fireEvent.click(within(await rowOf(name)).getByRole('button', { name: 'Expand' }))
}

function groupOf(stage: string): HTMLElement {
  const group = screen.getByText(stage).closest('div')?.parentElement
  if (group === null || group === undefined) throw new Error(`the group of ${stage} holds no element`)
  return group
}

describe('the navigation', () => {
  beforeEach(() => {
    useUi.setState({ navDatabases: {}, canvasSystemId: null })
    vi.mocked(api.layout).mockResolvedValue(layoutAnswer({ stages: [], shared_suppliers: [] }))
  })

  it('folds a database until it is opened, with its count on its row', async () => {
    renderAt('/', <NavPane />)
    const held = counted('fixture')
    const link = await screen.findByRole('link', { name: /^fixture/ })
    expect(link).toHaveTextContent(String(held.processes))
    expect(link).toHaveAttribute('href', paths.explorer('fixture'))
    expect(screen.queryByRole('link', { name: 'Datasets' })).toBeNull()
    expect(within(await rowOf('fixture')).getByRole('button', { name: 'Expand' })).toBeInTheDocument()
  })

  it('lists a database’s sections and its search once it is opened', async () => {
    renderAt('/', <NavPane />)
    const row = await rowOf('fixture')
    fireEvent.click(within(row).getByRole('button', { name: 'Expand' }))
    for (const place of places('fixture')) expect(screen.getByRole('link', { name: place.title })).toHaveAttribute('href', place.to)
    expect(screen.getByRole('link', { name: 'Search' })).toHaveAttribute('href', paths.search('fixture'))
    expect(screen.getAllByRole('link', { name: 'Datasets' })).toHaveLength(1)
    expect(within(row).getByRole('button', { name: 'Collapse' })).toBeInTheDocument()
  })

  it("groups a system's processes by the arrangement's stages", async () => {
    vi.mocked(api.layout).mockResolvedValue(
      layoutAnswer({
        stages: [
          { stage: 'assembly', codes: ['widget'], regions: [] },
          { stage: 'materials', codes: ['frame'], regions: [] },
        ],
        shared_suppliers: [],
      }),
    )
    renderAt('/', <NavPane />)
    await openSystem('widget')
    const assembly = await screen.findByText('assembly')
    const materials = screen.getByText('materials')
    expect(assembly.compareDocumentPosition(materials) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(groupOf('assembly')).getByRole('link', { name: 'widget assembly' })).toBeInTheDocument()
    expect(within(groupOf('materials')).getByRole('link', { name: 'frame production' })).toBeInTheDocument()
    expect(screen.queryByText('no stage')).toBeNull()
  })

  it('lists a system without stages as one group of no stage', async () => {
    vi.mocked(api.layout).mockResolvedValue(layoutAnswer(system.value as unknown as ProductSystem))
    renderAt('/', <NavPane />)
    await openSystem('widget')
    await screen.findByText('no stage')
    expect(screen.getAllByText('no stage')).toHaveLength(1)
    expect(within(groupOf('no stage')).getByRole('link', { name: 'widget assembly' })).toBeInTheDocument()
    expect(within(groupOf('no stage')).getByRole('link', { name: 'frame production' })).toBeInTheDocument()
  })

  it('keeps the database the address is under open', async () => {
    renderAt(paths.explorer('looped', 'flows'), <NavPane />)
    const opened = await screen.findAllByRole('link', { name: 'Datasets' })
    expect(opened).toHaveLength(1)
    expect(opened[0]).toHaveAttribute('href', paths.explorer('looped'))
    expect(screen.getByRole('link', { name: 'Elementary flows' })).toHaveAttribute('href', paths.explorer('looped', 'flows'))
    expect(screen.getByRole('link', { name: 'Search' })).toHaveAttribute('href', paths.search('looped'))
    expect(within(await rowOf('fixture')).getByRole('button', { name: 'Expand' })).toBeInTheDocument()
  })
})
