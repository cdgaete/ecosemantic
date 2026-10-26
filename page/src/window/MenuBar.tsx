import { Menu as MenuIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useReleaseCards, useSystem } from '@/api/queries'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Menubar, MenubarContent, MenubarItem, MenubarMenu, MenubarSub, MenubarSubContent, MenubarSubTrigger, MenubarTrigger } from '@/components/ui/menubar'
import { useResultParams } from '@/editors/results/useResultParams'
import { useGo } from '@/lib/paths'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useFiles } from './files'
import { menus, type MenuItem } from './menus'
import { runCanvas } from './shortcuts'
import { openNavigation } from './navigation'
import { Palette } from './Palette'
import { useMinWidth } from './useMinWidth'

interface Parts {
  Item: (props: { disabled?: boolean; onSelect?: () => void; asChild?: boolean; children: ReactNode }) => ReactNode
  Sub: (props: { children: ReactNode }) => ReactNode
  SubTrigger: (props: { disabled?: boolean; children: ReactNode }) => ReactNode
  SubContent: (props: { children: ReactNode }) => ReactNode
}

const BAR: Parts = { Item: MenubarItem, Sub: MenubarSub, SubTrigger: MenubarSubTrigger, SubContent: MenubarSubContent }
const DROPDOWN: Parts = { Item: DropdownMenuItem, Sub: DropdownMenuSub, SubTrigger: DropdownMenuSubTrigger, SubContent: DropdownMenuSubContent }

function Items({ items, parts, go }: { items: MenuItem[]; parts: Parts; go: (path: string) => void }) {
  const { Item, Sub, SubTrigger, SubContent } = parts
  return (
    <>
      {items.map((item) =>
        item.items ? (
          <Sub key={item.key}>
            <SubTrigger disabled={item.disabled}>{item.label}</SubTrigger>
            <SubContent>
              <Items items={item.items} parts={parts} go={go} />
            </SubContent>
          </Sub>
        ) : item.href ? (
          <Item key={item.key} disabled={item.disabled} asChild>
            <a href={item.href} download>
              {item.label}
            </a>
          </Item>
        ) : (
          <Item key={item.key} disabled={item.disabled} onSelect={() => (item.to ? go(item.to) : item.run?.())}>
            {item.label}
          </Item>
        ),
      )}
    </>
  )
}

export function MenuBar() {
  const go = useGo()
  const location = useLocation()
  const wide = useMinWidth(1024)
  const systemId = useUi((s) => s.canvasSystemId)
  const theme = useUi((s) => s.theme)
  const setTheme = useUi((s) => s.setTheme)
  const panelMode = useUi((s) => s.panelMode)
  const setPanelMode = useUi((s) => s.setPanelMode)
  const openRequest = useRequestDialog((s) => s.open)
  const read = useSystem(systemId ?? '', systemId !== null)
  const resolved = useResultParams(systemId ?? '', location.search)
  const files = useFiles()
  const release = useReleaseCards(systemId ?? '')
  const onResult = systemId !== null && location.pathname.startsWith(`/systems/${systemId}/results/`) && !location.pathname.endsWith('/setup')
  const all = menus({
    systemId,
    resultOpen: onResult && resolved.params !== null,
    openRequests: read.data?.open_requests ?? 0,
    theme,
    openNavigation,
    importFile: files.importFile,
    downloadResult: files.downloadResult,
    panelMode,
    setPanelMode,
    setTheme,
    newRequest: () => systemId && openRequest({ systemId }),
    reorganise: () => runCanvas('reorganise'),
    resetLayout: () => release.mutate(),
  })
  if (wide)
    return (
      <>
        <Menubar>
          {all.map((menu) => (
            <MenubarMenu key={menu.key}>
              <MenubarTrigger>{menu.label}</MenubarTrigger>
              <MenubarContent>
                <Items items={menu.items} parts={BAR} go={go} />
              </MenubarContent>
            </MenubarMenu>
          ))}
        </Menubar>
        {files.dialog}
        <Palette menus={all} go={go} />
      </>
    )
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger aria-label="Menu">
          <MenuIcon className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <Items items={all.map((menu) => ({ key: menu.key, label: menu.label, items: menu.items }))} parts={DROPDOWN} go={go} />
        </DropdownMenuContent>
      </DropdownMenu>
      {files.dialog}
      <Palette menus={all} go={go} />
    </>
  )
}
