import { Menu as MenuIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Menubar, MenubarContent, MenubarItem, MenubarMenu, MenubarSub, MenubarSubContent, MenubarSubTrigger, MenubarTrigger } from '@/components/ui/menubar'
import { ICON_BUTTON } from './IconButton'
import type { Menu, MenuItem } from './menus'

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

export function MenuStrip({ menus, go }: { menus: Menu[]; go: (path: string) => void }) {
  return (
    <Menubar>
      {menus.map((menu) => (
        <MenubarMenu key={menu.key}>
          <MenubarTrigger>{menu.label}</MenubarTrigger>
          <MenubarContent>
            <Items items={menu.items} parts={BAR} go={go} />
          </MenubarContent>
        </MenubarMenu>
      ))}
    </Menubar>
  )
}

export function MenuButton({ menus, go }: { menus: Menu[]; go: (path: string) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label="Menus" className={ICON_BUTTON}>
        <MenuIcon className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="grid grid-cols-[repeat(4,minmax(140px,1fr))] gap-x-2">
        {menus.map((menu) => (
          <div key={menu.key} className="min-w-0">
            <div className="px-2 py-1 text-xs font-semibold">{menu.label}</div>
            <Items items={menu.items} parts={DROPDOWN} go={go} />
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
