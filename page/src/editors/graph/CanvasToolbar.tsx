import { Ellipsis, LocateFixed, Maximize } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ProductSystem } from '@/api/types'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useUi } from '@/store/ui'
import { ICON_BUTTON, IconButton } from '@/window/IconButton'
import { keysOf } from '@/window/shortcuts'
import { useMinWidth } from '@/window/useMinWidth'

export interface CanvasToolbarProps {
  system: ProductSystem
  calculate?: ReactNode
  notes: string[]
  following: boolean
  fit: () => void
  follow: () => void
  scaling: string | null
  minimap: boolean
  setMinimapOpen: (open: boolean) => void
  focus: () => void
  reorganise: () => void
  reset: () => void
}

export function CanvasToolbar({ system, calculate, notes, following, fit, follow, scaling, minimap, setMinimapOpen, focus, reorganise, reset }: CanvasToolbarProps) {
  const variant = useUi((s) => (s.canvasSystemId === system.id ? s.canvasVariant : null))
  const setVariant = useUi((s) => s.setCanvasVariant)
  const scaledView = useUi((s) => s.scaledView)
  const setScaledView = useUi((s) => s.setScaledView)
  const formulaValues = useUi((s) => s.formulaValues)
  const setFormulaValues = useUi((s) => s.setFormulaValues)
  const scaledAvailable = scaling === null
  const scaledShown = scaledView && scaledAvailable
  const labelled = useMinWidth(1280)
  return (
    <div className="flex max-w-full flex-col items-center gap-1">
      <div
        role="toolbar"
        aria-label="Canvas"
        className="flex max-w-full flex-wrap items-center justify-center gap-1 rounded-xl border bg-chrome/95 p-1 shadow-lg backdrop-blur"
      >
        {calculate ? (
          <>
            {calculate}
            <span className="mx-0.5 h-5 w-px bg-border" />
          </>
        ) : null}
        <label className="flex min-w-0 items-center gap-1 px-1 text-xs">
          State
          <select
            aria-label="State"
            className="nodrag min-w-28 max-w-48 rounded-sm border bg-background px-1"
            value={variant ?? ''}
            onChange={(e) => setVariant(e.target.value === '' ? null : e.target.value)}
          >
            <option value="">base values</option>
            {system.cases.map((c) => (
              <option key={`case:${c.name}`} value={c.name}>
                case {c.name}
              </option>
            ))}
            {system.scenarios.map((sc) => (
              <option key={`scenario:${sc.name}`} value={sc.name}>
                scenario {sc.name}
              </option>
            ))}
          </select>
        </label>
        <span className="mx-0.5 h-5 w-px bg-border" />
        <IconButton label="Fit the graph" shortcut="fit" side="bottom" onClick={fit}>
          <Maximize />
        </IconButton>
        {following ? null : labelled ? (
          <Button size="sm" variant="ghost" onClick={follow}>
            <LocateFixed className="size-3.5" /> Follow the build
          </Button>
        ) : (
          <IconButton label="Follow the build" side="bottom" onClick={follow}>
            <LocateFixed />
          </IconButton>
        )}
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger aria-label="More canvas options" className={ICON_BUTTON}>
                <Ellipsis />
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="bottom" sideOffset={6}>
              More canvas options
            </TooltipContent>
          </Tooltip>
          <DropdownMenuContent side="bottom" align="end" className="w-64">
            <DropdownMenuCheckboxItem
              checked={scaledShown}
              disabled={!scaledAvailable}
              onCheckedChange={(on) => setScaledView(on === true)}
              className="flex-wrap"
            >
              Scaled to 1 unit
              {scaling === null ? null : <span className="basis-full text-xs text-muted-foreground">{scaling}</span>}
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem checked={formulaValues} onCheckedChange={(on) => setFormulaValues(on === true)}>
              Formula values
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem checked={minimap} onCheckedChange={(on) => setMinimapOpen(on === true)}>
              Minimap
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={focus}>
              Focus the reference process
              <DropdownMenuShortcut>{keysOf('focus')}</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={reorganise}>
              Reorganise the graph
              <DropdownMenuShortcut>{keysOf('reorganise')}</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={reset}>Reset layout</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {notes.length > 0 ? (
        <p role="status" className="max-w-full rounded-md bg-chrome/95 px-2 py-0.5 text-center text-xs shadow">
          {notes.map((note) => (
            <span key={note} className="block">
              {note}
            </span>
          ))}
        </p>
      ) : null}
    </div>
  )
}
