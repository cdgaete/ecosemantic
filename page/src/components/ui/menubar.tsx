import * as React from 'react'
import * as MenubarPrimitive from '@radix-ui/react-menubar'
import { ChevronRightIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

const CONTENT =
  'bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 z-50 min-w-[12rem] overflow-hidden rounded-md border p-1 shadow-md'
const ITEM =
  'focus:bg-accent focus:text-accent-foreground relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-xs outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50'

function Menubar({ className, ...props }: React.ComponentProps<typeof MenubarPrimitive.Root>) {
  return <MenubarPrimitive.Root data-slot="menubar" className={cn('flex items-center gap-0.5', className)} {...props} />
}

function MenubarMenu({ ...props }: React.ComponentProps<typeof MenubarPrimitive.Menu>) {
  return <MenubarPrimitive.Menu data-slot="menubar-menu" {...props} />
}

function MenubarTrigger({ className, ...props }: React.ComponentProps<typeof MenubarPrimitive.Trigger>) {
  return (
    <MenubarPrimitive.Trigger
      data-slot="menubar-trigger"
      className={cn('focus:bg-accent data-[state=open]:bg-accent flex items-center rounded-sm px-2 py-0.5 text-xs outline-hidden select-none', className)}
      {...props}
    />
  )
}

function MenubarContent({ className, align = 'start', sideOffset = 4, ...props }: React.ComponentProps<typeof MenubarPrimitive.Content>) {
  return (
    <MenubarPrimitive.Portal>
      <MenubarPrimitive.Content data-slot="menubar-content" align={align} sideOffset={sideOffset} className={cn(CONTENT, className)} {...props} />
    </MenubarPrimitive.Portal>
  )
}

function MenubarItem({ className, ...props }: React.ComponentProps<typeof MenubarPrimitive.Item>) {
  return <MenubarPrimitive.Item data-slot="menubar-item" className={cn(ITEM, className)} {...props} />
}

function MenubarSub({ ...props }: React.ComponentProps<typeof MenubarPrimitive.Sub>) {
  return <MenubarPrimitive.Sub data-slot="menubar-sub" {...props} />
}

function MenubarSubTrigger({ className, children, ...props }: React.ComponentProps<typeof MenubarPrimitive.SubTrigger>) {
  return (
    <MenubarPrimitive.SubTrigger data-slot="menubar-sub-trigger" className={cn(ITEM, 'data-[state=open]:bg-accent', className)} {...props}>
      {children}
      <ChevronRightIcon className="ml-auto size-3.5" />
    </MenubarPrimitive.SubTrigger>
  )
}

function MenubarSubContent({ className, ...props }: React.ComponentProps<typeof MenubarPrimitive.SubContent>) {
  return (
    <MenubarPrimitive.Portal>
      <MenubarPrimitive.SubContent data-slot="menubar-sub-content" className={cn(CONTENT, className)} {...props} />
    </MenubarPrimitive.Portal>
  )
}

export { Menubar, MenubarMenu, MenubarTrigger, MenubarContent, MenubarItem, MenubarSub, MenubarSubTrigger, MenubarSubContent }
