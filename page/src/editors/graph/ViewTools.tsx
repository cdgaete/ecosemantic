import { useReactFlow, useStore } from '@xyflow/react'
import { Info, Map as MapIcon, ZoomIn, ZoomOut } from 'lucide-react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { ICON_BUTTON, IconButton } from '@/window/IconButton'
import { useMinWidth } from '@/window/useMinWidth'

const MOVE = { duration: 250 }

const LAYOUT = 'One column per step away from the functional unit, which sits at the right. A solid outline marks the cards changed by the entries since you last looked, or by the chosen entry, in the colour of the agent that wrote them. An amber ring marks the values those entries changed. A dashed outline marks the selected card. Drag a card to keep its place.'

interface ViewToolsProps {
  pause: () => void
  minimap: boolean
  setMinimapOpen: (open: boolean) => void
}

export function ViewTools({ pause, minimap, setMinimapOpen }: ViewToolsProps) {
  const flow = useReactFlow()
  const zoom = useStore((s) => s.transform[2])
  const narrow = !useMinWidth(768)
  const side = narrow ? 'top' : 'right'
  const zoomBy = (direction: 'in' | 'out') => {
    pause()
    void (direction === 'in' ? flow.zoomIn(MOVE) : flow.zoomOut(MOVE))
  }
  const zoomIn = (
    <IconButton label="Zoom in" side={side} onClick={() => zoomBy('in')}>
      <ZoomIn />
    </IconButton>
  )
  const zoomOut = (
    <IconButton label="Zoom out" side={side} onClick={() => zoomBy('out')}>
      <ZoomOut />
    </IconButton>
  )
  const percent = (
    <span aria-label="Zoom level" className={cn('text-center text-xs tabular-nums text-muted-foreground', narrow ? 'min-w-11' : 'w-full')}>
      {Math.round(zoom * 100)}%
    </span>
  )
  return (
    <div className={cn('flex gap-0.5', narrow ? 'flex-row items-center' : 'flex-col items-center')}>
      {narrow ? (
        <>
          {zoomOut}
          {percent}
          {zoomIn}
        </>
      ) : (
        <>
          {zoomIn}
          {percent}
          {zoomOut}
        </>
      )}
      <IconButton label="Minimap" side={side} pressed={minimap} onClick={() => setMinimapOpen(!minimap)}>
        <MapIcon />
      </IconButton>
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger aria-label="About this layout" className={ICON_BUTTON}>
              <Info />
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side={side} sideOffset={6}>
            About this layout
          </TooltipContent>
        </Tooltip>
        <DropdownMenuContent side={side} align="start" className="w-72">
          <p className="text-xs text-muted-foreground">{LAYOUT}</p>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
