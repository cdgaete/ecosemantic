import { PanelLeft, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import { useServer, useSystem } from '@/api/queries'
import logo from '@/assets/logo.svg'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { useUi } from '@/store/ui'
import { RequestsBadge, ValidationBadge } from './Badges'
import { IconButton } from './IconButton'
import { LiveStatus } from './LiveStatus'
import { DOCKS_FROM, toggleNavigation } from './navigation'
import { useMinWidth } from './useMinWidth'

export function TopBar({ menu }: { menu: ReactNode }) {
  const systemId = useUi((s) => s.canvasSystemId)
  const read = useSystem(systemId ?? '', systemId !== null)
  const info = useServer()
  const client = info.data?.client ?? null
  const docked = useUi((s) => s.navDocked)
  const navOpen = useUi((s) => s.navOpen)
  const shown = useMinWidth(DOCKS_FROM) ? docked : navOpen
  const setPaletteOpen = useUi((s) => s.setPaletteOpen)
  return (
    <header className="border-b bg-chrome text-xs">
      <div className="flex items-center gap-3 px-2.5 py-1">
        <IconButton label={shown ? 'Hide navigation' : 'Show navigation'} shortcut="navigation" pressed={shown} onClick={toggleNavigation}>
          <PanelLeft />
        </IconButton>
        {menu}
        <span className="flex items-center gap-1.5">
          <img src={logo} alt="EcoSemantic" className="size-4 shrink-0" />
          <AppLink to={paths.home()} className="font-semibold hover:underline">
            EcoSemantic
          </AppLink>
        </span>
        {client ? <span className="truncate text-muted-foreground">Connected: {client.name}</span> : null}
        <span className="ml-auto">
          <IconButton label="Go to anything" shortcut="palette" onClick={() => setPaletteOpen(true)}>
            <Search />
          </IconButton>
        </span>
      </div>
      {systemId ? (
        <div className="flex items-center justify-between gap-3 border-t px-2.5 py-1">
          <span className="truncate font-semibold">{read.data?.value.name ?? ''}</span>
          <span className="flex items-center gap-3 text-muted-foreground">
            <ValidationBadge id={systemId} />
            <RequestsBadge id={systemId} />
            <LiveStatus />
          </span>
        </div>
      ) : null}
    </header>
  )
}
