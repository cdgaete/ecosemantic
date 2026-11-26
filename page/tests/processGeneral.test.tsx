import { screen, within } from '@testing-library/react'
import type { Process } from '@/api/types'
import { ProcessGeneralPage } from '@/editors/process/ProcessGeneralPage'
import { renderAt } from './render'

const baking: Process = {
  id: 'process-1',
  code: 'bread-baking',
  name: 'Bread baking',
  unit: 'kg',
  location: 'CH',
  reference_product: 'bread',
  comment: null,
  metadata: {},
  exchanges: [],
}

function renderProcess(process: Process) {
  return renderAt('/', <ProcessGeneralPage systemId="system-1" process={process} />)
}

const sectionOf = (title: string) => screen.getByText(title).closest('section') as HTMLElement

const rowOf = (section: HTMLElement, label: string) =>
  within(section).getAllByText(label).map((dt) => dt.nextElementSibling?.textContent ?? '')

it('says a process carries no metadata in one sentence, keeping the request action', () => {
  renderProcess(baking)
  const metadata = sectionOf('Metadata')
  expect(within(metadata).getByText('No metadata provided')).toBeInTheDocument()
  expect(within(metadata).queryByText('Life-cycle stage')).toBeNull()
  expect(within(metadata).getByRole('button', { name: 'Request' })).toBeInTheDocument()
})

it('names an absent comment with one sentence instead of an empty value', () => {
  renderProcess(baking)
  expect(rowOf(sectionOf('General information'), 'Comment')).toEqual(['No comment provided'])
})

it('keeps the field labels of a section whose metadata is partly present', () => {
  renderProcess({ ...baking, metadata: { life_cycle_stage: 'agriculture', hierarchy_level: null } })
  const metadata = sectionOf('Metadata')
  expect(within(metadata).queryByText('No metadata provided')).toBeNull()
  expect(rowOf(metadata, 'Life-cycle stage')).toEqual(['agriculture'])
  expect(rowOf(metadata, 'Hierarchy level')).toEqual(['Not provided'])
  expect(rowOf(metadata, 'Supply-chain tier')).toEqual(['Not provided'])
})

it('reads a numeric zero and a false as themselves, not as a missing value', () => {
  renderProcess({ ...baking, metadata: { hierarchy_level: 0, supply_chain_tier: 0, life_cycle_stage: false } })
  const metadata = sectionOf('Metadata')
  expect(rowOf(metadata, 'Hierarchy level')).toEqual(['0'])
  expect(rowOf(metadata, 'Supply-chain tier')).toEqual(['0'])
  expect(rowOf(metadata, 'Life-cycle stage')).toEqual(['false'])
})

it('reads an absent name and location as not provided while a comment is shown', () => {
  renderProcess({ ...baking, name: '', location: '', comment: 'Baked for the retail case.' })
  const general = sectionOf('General information')
  expect(rowOf(general, 'Name')).toEqual(['Not provided'])
  expect(rowOf(general, 'Location')).toEqual(['Not provided'])
  expect(rowOf(general, 'Comment')).toEqual(['Baked for the retail case.'])
})
