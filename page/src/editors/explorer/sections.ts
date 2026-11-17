import type { DatabaseSummary } from '@/api/types'
import type { ExplorerSection } from '@/lib/paths'
import { BarChart3, FolderTree, Leaf, MapPin, Ruler, type LucideIcon } from 'lucide-react'

export interface SectionEntry {
  section: ExplorerSection
  title: string
  count: keyof DatabaseSummary
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

export function isSection(value: string): value is ExplorerSection {
  return SECTIONS.some((entry) => entry.section === value)
}
