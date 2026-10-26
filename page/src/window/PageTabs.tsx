import { useLocation } from 'react-router-dom'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'

export interface PageTab {
  key: string
  label: string
  path: string
}

export function PageTabs({ pages, active }: { pages: PageTab[]; active: string }) {
  const location = useLocation()
  return (
    <nav className="flex flex-wrap gap-1 border-t bg-chrome p-1" aria-label="Pages">
      {pages.map((page) => (
        <AppLink
          key={page.key}
          to={page.path}
          aria-current={page.key === active ? 'page' : undefined}
          className={cn('rounded-md px-2.5 py-1 text-xs whitespace-nowrap text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground', page.key === active && 'bg-background text-foreground shadow-sm')}
          state={{ from: location.pathname }}
        >
          {page.label}
        </AppLink>
      ))}
    </nav>
  )
}
