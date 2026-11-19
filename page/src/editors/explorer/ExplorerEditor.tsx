import { useEffect } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { NoEditor } from '@/editors/NoEditor'
import { useAddress, type Patch } from '@/lib/address'
import { paths, type ExplorerSection, type SearchKind } from '@/lib/paths'
import { useEditorTab } from '@/window/useEditorTab'
import { DatasetsSection } from './DatasetsSection'
import { FlowsSection } from './FlowsSection'
import { ListSection } from './ListSection'
import { MethodsSection } from './MethodsSection'
import { SectionBar } from './SectionBar'
import { isSection, SEARCHED_SECTIONS, TITLES } from './sections'

interface Place {
  section: ExplorerSection
  item: string
  searching: boolean
}

function isSearchKind(value: string): value is SearchKind {
  return Object.hasOwn(SEARCHED_SECTIONS, value)
}

function placeOf(rest: string): Place | null {
  const parts = rest.split('/').filter((part) => part.length > 0)
  const [head = '', ...tail] = parts
  if (head === '') return { section: 'datasets', item: '', searching: false }
  if (head === 'processes') return { section: 'datasets', item: tail.join('/'), searching: false }
  if (head === 'search') {
    const kind = tail[0] ?? ''
    return isSearchKind(kind) ? { section: SEARCHED_SECTIONS[kind], item: '', searching: true } : null
  }
  return isSection(head) ? { section: head, item: tail.join('/'), searching: false } : null
}

export function ExplorerEditor() {
  const params = useParams()
  const name = params.name ?? ''
  const rest = params['*'] ?? ''
  const location = useLocation()
  const address = useAddress()
  const place = placeOf(rest)
  const section = place?.section ?? null
  const tab = section === null ? null : { id: `explorer:${name}:${section}`, kind: 'explorer' as const, title: `${name} · ${TITLES[section]}`, path: `${paths.explorer(name, section)}${location.search}` }
  useEditorTab(tab)
  useEffect(() => {
    const patch: Patch = {}
    if (place?.searching === true && address.read('whole') === '') patch.whole = '1'
    if (place !== null && place.item !== '' && address.read('item') === '') patch.item = place.item
    if (Object.keys(patch).length > 0) address.write(patch)
  }, [place, address])
  if (place === null) return <NoEditor />
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <SectionBar name={name} section={place.section} />
      {place.section === 'datasets' ? <DatasetsSection name={name} /> : null}
      {place.section === 'flows' ? <FlowsSection name={name} /> : null}
      {place.section === 'methods' ? <MethodsSection name={name} /> : null}
      {place.section === 'units' || place.section === 'locations' ? <ListSection key={place.section} name={name} kind={place.section} /> : null}
    </div>
  )
}
