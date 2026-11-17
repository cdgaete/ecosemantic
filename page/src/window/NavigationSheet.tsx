import { X } from 'lucide-react'
import { useUi } from '@/store/ui'
import { closeNavigation } from './navigation'
import { IconButton } from './IconButton'
import { NavPane } from './NavPane'

export function NavigationSheet() {
  const open = useUi((s) => s.navOpen)
  if (!open) return null
  return (
    <aside
      aria-label="Navigation"
      className="col-start-2 row-span-3 row-start-1 z-10 flex w-[352px] max-w-full min-w-0 flex-col self-stretch justify-self-start overflow-hidden rounded-xl border bg-background shadow-lg"
    >
      <div className="flex items-center justify-between gap-2 border-b bg-chrome py-0.5 pr-0.5 pl-3 text-xs font-semibold">
        Navigation
        <IconButton label="Close navigation" onClick={closeNavigation}>
          <X />
        </IconButton>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <NavPane />
      </div>
    </aside>
  )
}
