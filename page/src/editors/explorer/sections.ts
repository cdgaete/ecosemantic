import type { DatabaseSummary } from '@/api/types'
import { paths, type ExplorerSection, type SearchKind } from '@/lib/paths'
import { BarChart3, FolderTree, Leaf, MapPin, Ruler, Search, type LucideIcon } from 'lucide-react'

export interface SectionEntry {
  section: ExplorerSection
  title: string
  count: keyof DatabaseSummary
  icon: LucideIcon
}

export interface Place {
  key: string
  title: string
  to: string
  icon: LucideIcon
}

export const SECTIONS: SectionEntry[] = [
  { section: 'datasets', title: 'Datasets', count: 'processes', icon: FolderTree },
  { section: 'flows', title: 'Elementary flows', count: 'elementary_flows', icon: Leaf },
  { section: 'methods', title: 'Impact methods', count: 'indicators', icon: BarChart3 },
  { section: 'units', title: 'Units', count: 'units', icon: Ruler },
  { section: 'locations', title: 'Locations', count: 'locations', icon: MapPin },
]

export const TITLES = Object.fromEntries(SECTIONS.map((entry) => [entry.section, entry.title])) as Record<ExplorerSection, string>

export const SEARCHED_SECTIONS: Record<SearchKind, ExplorerSection> = {
  processes: 'datasets',
  'elementary-flows': 'flows',
  methods: 'methods',
}

export const SEARCHED: ExplorerSection[] = Object.values(SEARCHED_SECTIONS)

export function searchedFrom(section: ExplorerSection): ExplorerSection {
  return SEARCHED.includes(section) ? section : 'datasets'
}

export function isSection(value: string): value is ExplorerSection {
  return SECTIONS.some((entry) => entry.section === value)
}

export function places(database: string): Place[] {
  return [
    ...SECTIONS.map((entry) => ({ key: entry.section, title: entry.title, to: paths.explorer(database, entry.section), icon: entry.icon })),
    { key: 'search', title: 'Search', to: paths.search(database), icon: Search },
  ]
}
