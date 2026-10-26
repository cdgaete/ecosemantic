import { Command } from 'cmdk'
import { useSystem, useSystems } from '@/api/queries'
import { paths } from '@/lib/paths'
import { useUi } from '@/store/ui'
import type { Menu } from './menus'
import { leaves } from './palette'
import { SHORTCUTS } from './shortcuts'

const GROUP = '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-muted-foreground'
const ITEM = 'flex cursor-pointer items-center justify-between gap-3 rounded-md px-2 py-1.5 data-[selected=true]:bg-foreground/8'
const PAGES = [
  { key: 'general', label: 'General information' },
  { key: 'parameters', label: 'Parameters' },
  { key: 'statistics', label: 'Statistics' },
  { key: 'requests', label: 'Requests' },
  { key: 'simulations', label: 'Simulations' },
]

export function Palette({ menus, go }: { menus: Menu[]; go: (path: string) => void }) {
  const open = useUi((s) => s.paletteOpen)
  const setOpen = useUi((s) => s.setPaletteOpen)
  const systemId = useUi((s) => s.canvasSystemId)
  const systems = useSystems()
  const system = useSystem(systemId ?? '', systemId !== null)
  const run = (act: () => void) => {
    setOpen(false)
    act()
  }
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Command palette" loop overlayClassName="fixed inset-0 z-40 bg-black/40" contentClassName="fixed top-[18%] left-1/2 z-50 w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-2xl">
      <Command.Input placeholder="Go to a process, a page or a command…" className="w-full border-b bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground" />
      <Command.List className="max-h-[50vh] overflow-auto p-1 text-sm">
        <Command.Empty className="px-2 py-3 text-muted-foreground">Nothing matches.</Command.Empty>
        {systemId && system.data ? (
          <Command.Group heading={system.data.value.name} className={GROUP}>
            {system.data.value.processes.map((process) => (
              <Command.Item key={process.id} value={`process ${process.name} ${process.code}`} className={ITEM} onSelect={() => run(() => go(paths.process(systemId, process.code)))}>
                {process.name}
                <span className="text-xs text-muted-foreground">process</span>
              </Command.Item>
            ))}
            {PAGES.map((page) => (
              <Command.Item key={page.key} value={`page ${page.label}`} className={ITEM} onSelect={() => run(() => go(paths.systemPage(systemId, page.key)))}>
                {page.label}
                <span className="text-xs text-muted-foreground">page</span>
              </Command.Item>
            ))}
          </Command.Group>
        ) : null}
        <Command.Group heading="Product systems" className={GROUP}>
          {(systems.data?.value ?? []).map((listed) => (
            <Command.Item key={listed.id} value={`system ${listed.name}`} className={ITEM} onSelect={() => run(() => go(paths.system(listed.id)))}>
              {listed.name}
              <span className="text-xs text-muted-foreground">{listed.database}</span>
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading="Commands" className={GROUP}>
          {leaves(menus).map((leaf) =>
            leaf.item.href ? (
              <Command.Item key={leaf.key} value={leaf.label} className={ITEM} onSelect={() => run(() => window.location.assign(leaf.item.href ?? ''))}>
                {leaf.label}
              </Command.Item>
            ) : (
              <Command.Item key={leaf.key} value={leaf.label} className={ITEM} onSelect={() => run(() => (leaf.item.to ? go(leaf.item.to) : leaf.item.run?.()))}>
                {leaf.label}
              </Command.Item>
            ),
          )}
        </Command.Group>
        <Command.Group heading="Shortcuts" className={GROUP}>
          {SHORTCUTS.map((shortcut) => (
            <Command.Item key={shortcut.id} value={`shortcut ${shortcut.label} ${shortcut.keys}`} className={ITEM} onSelect={() => run(shortcut.run)}>
              {shortcut.label}
              <kbd className="font-sans text-xs text-muted-foreground">{shortcut.keys}</kbd>
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  )
}
