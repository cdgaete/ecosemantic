import { ExternalLink, Ellipsis, Play, RotateCw } from 'lucide-react'
import type { Call } from '@/api/types'
import { useSystem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { CalculateButton } from '@/editors/system/CalculateButton'
import { categoryLabel, formatAmount, methodById } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { IconButton } from '@/window/IconButton'
import { useMinWidth } from '@/window/useMinWidth'
import type { CanvasVariant } from '@/window/useCanvasState'
import { useChooseCase } from '@/window/useChooseCase'
import { NEW_CALCULATION, resultSearch, runAgainLabel } from './calculations'
import { serializeParams, type ResultParams } from './params'
import { methodOf } from './recorded'
import { useStartImpact } from './useStartImpact'
import { useBand, type Band } from './useBand'

function Unscored({ systemId, params, state }: { systemId: string; params: ResultParams; state: CanvasVariant }) {
  const startImpact = useStartImpact(systemId)
  return (
    <span className="flex flex-wrap items-center justify-center gap-1">
      {`${state.kind} ${state.name}: not in this calculation`}
      <Button
        size="sm"
        variant="ghost"
        onClick={() => startImpact('impact', serializeParams({ ...params, variants: [...params.variants, state.name] }))}
      >
        Calculate with it
      </Button>
    </span>
  )
}

/** Opens the result a calculation computed, repeats it, or opens the form that starts another. Words from
 * 1280 px, icons with tooltips from 768 px, and below 768 px the first in words beside a labelled menu. */
export function CalculationActions({ systemId, call, search = '' }: { systemId: string; call?: Call; search?: string }) {
  const go = useGo()
  const startImpact = useStartImpact(systemId)
  const database = useSystem(systemId).data?.value.database.name ?? ''
  const labelled = useMinWidth(1280)
  const wide = useMinWidth(768)
  const repeat = call === undefined ? '' : runAgainLabel(call, database)
  const open = () => go(paths.results(systemId, 'impact', search))
  const again = () => call !== undefined && startImpact('impact', `?call=${call.id}`)
  const fresh = () => go(paths.results(systemId, 'setup', ''))
  const buttons = call === undefined ? (
    <Button size="sm" variant="ghost" onClick={fresh}>
      <Play className="size-3.5" /> {NEW_CALCULATION}
    </Button>
  ) : !wide ? (
    <>
      <Button size="sm" variant="ghost" onClick={open}>
        <ExternalLink className="size-3.5" /> Open result
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
          <Ellipsis /> More calculation actions
        </DropdownMenuTrigger>
        <DropdownMenuContent side="bottom" align="end" className="w-72">
          <DropdownMenuItem onSelect={again}>{repeat}</DropdownMenuItem>
          <DropdownMenuItem onSelect={fresh}>{NEW_CALCULATION}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  ) : !labelled ? (
    <>
      <IconButton label="Open result" onClick={open}>
        <ExternalLink />
      </IconButton>
      <IconButton label={repeat} onClick={again}>
        <RotateCw />
      </IconButton>
      <IconButton label={NEW_CALCULATION} onClick={fresh}>
        <Play />
      </IconButton>
    </>
  ) : (
    <>
      <Button size="sm" variant="ghost" onClick={open}>
        <ExternalLink className="size-3.5" /> Open result
      </Button>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button size="sm" variant="ghost" aria-label={repeat} onClick={again}>
            <RotateCw className="size-3.5" /> Run again
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          {repeat}
        </TooltipContent>
      </Tooltip>
      <Button size="sm" variant="ghost" onClick={fresh}>
        <Play className="size-3.5" /> {NEW_CALCULATION}
      </Button>
    </>
  )
  return (
    <span role="group" aria-label="Calculation actions" className="flex shrink-0 items-center gap-1">
      {buttons}
    </span>
  )
}

function Row({ systemId, band }: { systemId: string; band: Band }) {
  const system = useSystem(systemId).data?.value
  const chooseCase = useChooseCase(systemId)
  const unit = band.chosen === undefined ? null : band.chosen.unit
  const method = methodOf(band.call, system?.database.name ?? '')
  return (
    <>
      <span className="max-w-56 truncate px-1 text-xs" title={method}>
        {method}
      </span>
      {band.categories.length > 1 ? (
        <select
          aria-label="Category"
          className="nodrag max-w-48 rounded-sm border bg-background px-1 text-xs"
          value={band.chosen?.method_id ?? ''}
          onChange={(e) => band.choose(e.target.value)}
        >
          {band.categories.map((category) => (
            <option key={category.method_id} value={category.method_id}>
              {categoryLabel(methodById(band.methods, category.method_id))}
            </option>
          ))}
        </select>
      ) : band.chosen === undefined ? null : (
        <span className="px-1 text-xs">{categoryLabel(methodById(band.methods, band.chosen.method_id))}</span>
      )}
      <div role="group" aria-label="Case shown" className="flex flex-wrap items-center gap-1">
        {band.cases.map((one) => {
          const pressed = one.name === null ? band.variant === null && band.unscored === null : one.name === band.variant
          return (
            <Button
              key={one.name ?? 'base'}
              size="sm"
              variant={pressed ? 'secondary' : 'ghost'}
              aria-pressed={pressed}
              disabled={!one.held}
              onClick={() => chooseCase(one.name)}
            >
              {one.name ?? 'Base values'}
              {one.score === null || unit === null ? null : ` ${formatAmount(one.score)} ${unit}`}
              {one.held ? null : ' not in the system'}
            </Button>
          )
        })}
      </div>
      <CalculationActions systemId={systemId} call={band.call} search={resultSearch(band)} />
      {band.hashLine === null && band.unscored === null ? null : (
        <p role="status" className="basis-full rounded-md bg-chrome/95 px-2 py-0.5 text-center text-xs shadow">
          {band.hashLine === null ? null : <span className="block">{band.hashLine}</span>}
          {band.unscored === null ? null : <Unscored systemId={systemId} params={band.params} state={band.unscored} />}
        </p>
      )}
    </>
  )
}

/** The canvas's first group: the latest successful calculation's method and category, the base and each
 * case it scored as the canvas's state, and the ways to open, repeat or start a calculation. */
export function ResultBand({ systemId }: { systemId: string }) {
  const band = useBand(systemId)
  return (
    <div role="group" aria-label="Result band" className="contents">
      {band === null ? <CalculateButton systemId={systemId} /> : <Row systemId={systemId} band={band} />}
    </div>
  )
}
