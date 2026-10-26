import type { Menu, MenuItem } from './menus'

export interface Leaf {
  key: string
  label: string
  item: MenuItem
}

function under(path: string, items: MenuItem[]): Leaf[] {
  return items.flatMap((item) => {
    if (item.disabled) return []
    const label = `${path} › ${item.label}`
    return item.items ? under(label, item.items) : [{ key: item.key, label, item }]
  })
}

export function leaves(menus: Menu[]): Leaf[] {
  return menus.flatMap((menu) => under(menu.label, menu.items))
}
