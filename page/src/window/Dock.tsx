import { Moon, PanelLeft, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import logo from '@/assets/logo.svg'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { IconButton } from './IconButton'
import { toggleNavigation } from './navigation'
import { useMinWidth } from './useMinWidth'

export function Dock({ menus, view = null }: { menus: ReactNode; view?: ReactNode }) {
  const navOpen = useUi((s) => s.navOpen)
  const setPaletteOpen = useUi((s) => s.setPaletteOpen)
  const dark = useUi((s) => s.theme === 'dark')
  const setTheme = useUi((s) => s.setTheme)
  const narrow = !useMinWidth(768)
  return (
    <div
      role="toolbar"
      aria-label="Frame"
      aria-orientation={narrow ? 'horizontal' : 'vertical'}
      data-clear={narrow ? 'top' : 'left'}
      className={cn(
        'col-start-1 row-start-1 flex items-center gap-0.5 rounded-xl border bg-chrome/95 p-1 shadow-lg',
        narrow ? 'flex-row self-stretch' : 'row-span-2 flex-col self-start',
      )}
    >
      <AppLink to={paths.home()} aria-label="EcoSemantic: all product systems" className={cn('flex size-7 items-center justify-center rounded-md hover:bg-foreground/8', !narrow && 'mb-1')}>
        <img src={logo} alt="" className="size-5 shrink-0" />
      </AppLink>
      {menus}
      <IconButton label="Navigation" shortcut="navigation" pressed={navOpen} onClick={toggleNavigation}>
        <PanelLeft />
      </IconButton>
      <IconButton label="Go to anything" shortcut="palette" onClick={() => setPaletteOpen(true)}>
        <Search />
      </IconButton>
      {view === null ? null : (
        <>
          <span aria-hidden className="my-0.5 h-px w-5 shrink-0 bg-border" />
          {view}
        </>
      )}
      <IconButton label="Dark theme" pressed={dark} onClick={() => setTheme(dark ? 'light' : 'dark')}>
        <Moon />
      </IconButton>
    </div>
  )
}
