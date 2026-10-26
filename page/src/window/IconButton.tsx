import type { ReactNode } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { keysOf } from './shortcuts'

interface IconButtonProps {
  label: string
  shortcut?: string
  pressed?: boolean
  side?: 'top' | 'right' | 'bottom' | 'left'
  className?: string
  onClick: () => void
  children: ReactNode
}

export const ICON_BUTTON =
  'flex size-7 shrink-0 items-center justify-center rounded-md text-foreground/80 transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground active:bg-foreground/10 focus-visible:outline-2 focus-visible:outline-ring [&_svg]:size-4'

export function IconButton({ label, shortcut, pressed, side = 'bottom', className, onClick, children }: IconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          aria-pressed={pressed}
          className={cn(ICON_BUTTON, pressed && 'bg-foreground/8 text-foreground', className)}
          onClick={onClick}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={6}>
        {label}
        {shortcut ? <kbd className="ml-2 font-sans opacity-70">{keysOf(shortcut)}</kbd> : null}
      </TooltipContent>
    </Tooltip>
  )
}
