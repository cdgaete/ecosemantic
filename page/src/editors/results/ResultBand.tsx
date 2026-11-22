import { ExternalLink, Play, RotateCw } from 'lucide-react'
import { useSystem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { CalculateButton } from '@/editors/system/CalculateButton'
import { categoryLabel, formatAmount, methodById } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { IconButton } from '@/window/IconButton'
import type { CanvasVariant } from '@/window/useCanvasState'
import { useChooseCase } from '@/window/useChooseCase'
import { serializeParams, type ResultParams } from './params'
import { methodOf, variantsOf } from './recorded'
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

function Row({ systemId, band }: { systemId: string; band: Band }) {
  const go = useGo()
  const system = useSystem(systemId).data?.value
  const chooseCase = useChooseCase(systemId)
  const startImpact = useStartImpact(systemId)
  const unit = band.chosen === undefined ? null : band.chosen.unit
  const method = methodOf(band.call, system?.database.name ?? '')
  const scored = variantsOf(band.call)
  const search = new URLSearchParams({ call: band.call.id })
  if (band.categories.length > 1 && band.chosen !== undefined) search.set('category', band.chosen.method_id)
  if (band.variant !== null) search.set('variant', band.variant)
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
      <Button size="sm" variant="ghost" onClick={() => go(paths.results(systemId, 'impact', `?${search.toString()}`))}>
        <ExternalLink className="size-3.5" /> Open result
      </Button>
      <IconButton label={`Calculate again: ${method} · ${scored.length > 0 ? scored.join(', ') : 'base values'}`} onClick={() => startImpact('impact', `?call=${band.call.id}`)}>
        <RotateCw />
      </IconButton>
      <IconButton label="New calculation" onClick={() => go(paths.results(systemId, 'setup', ''))}>
        <Play />
      </IconButton>
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
