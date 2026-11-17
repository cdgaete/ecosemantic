import { useSummary } from '@/api/queries'
import { formatAmount } from '@/lib/format'
import { paths, type ExplorerSection } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { Icon } from '@/window/Icon'
import { SECTIONS } from './sections'

export function SectionBar({ name, section }: { name: string; section: ExplorerSection }) {
  const summary = useSummary(name)
  const counts = summary.data?.value
  return (
    <header className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-b bg-chrome px-3 py-1.5">
      <h1 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold [overflow-wrap:anywhere]">
        <Icon name="database" />
        {name}
      </h1>
      <nav aria-label="Sections" className="flex min-w-0 flex-wrap items-center gap-1">
        {SECTIONS.map((entry) => (
          <AppLink
            key={entry.section}
            to={paths.explorer(name, entry.section)}
            aria-current={entry.section === section ? 'page' : undefined}
            className={cn(
              'rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground',
              entry.section === section && 'bg-background text-foreground shadow-sm',
            )}
          >
            <span>
              {entry.title} <span className="tabular-nums">{counts === undefined ? '' : formatAmount(counts[entry.count])}</span>
            </span>
          </AppLink>
        ))}
      </nav>
    </header>
  )
}
