import { Play, RotateCw } from 'lucide-react'
import { useCalculations, useSystem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { methodOf, latestOf, variantsOf } from '@/editors/results/recorded'
import { useStartImpact } from '@/editors/results/useStartImpact'
import { paths, useGo } from '@/lib/paths'
import { IconButton } from '@/window/IconButton'

/** Calculate, which opens the calculation form, and beside it the latest recorded calculation that succeeded, to run again in one click. */
export function CalculateButton({ systemId }: { systemId: string }) {
  const go = useGo()
  const startImpact = useStartImpact(systemId)
  const calculations = useCalculations(systemId)
  const database = useSystem(systemId).data?.value.database.name ?? ''
  const last = latestOf(calculations.data?.value ?? [])
  const variants = last === undefined ? [] : variantsOf(last)
  return (
    <>
      <Button size="sm" aria-label="Calculate an impact result" onClick={() => go(paths.results(systemId, 'setup', ''))}>
        <Play className="size-3.5" /> Calculate
      </Button>
      {last === undefined ? null : (
        <IconButton
          label={`Calculate again: ${methodOf(last, database)} · ${variants.length > 0 ? variants.join(', ') : 'base values'}`}
          onClick={() => startImpact('impact', `?call=${last.id}`)}
        >
          <RotateCw />
        </IconButton>
      )}
    </>
  )
}
