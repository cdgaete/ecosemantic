import { Play, RotateCw } from 'lucide-react'
import { useCalculations, useSystem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { NEW_CALCULATION, runAgainLabel } from '@/editors/results/calculations'
import { latestOf } from '@/editors/results/recorded'
import { useStartImpact } from '@/editors/results/useStartImpact'
import { paths, useGo } from '@/lib/paths'
import { IconButton } from '@/window/IconButton'

/** Opens the calculation form, and beside it repeats the latest recorded calculation that succeeded. */
export function CalculateButton({ systemId }: { systemId: string }) {
  const go = useGo()
  const startImpact = useStartImpact(systemId)
  const calculations = useCalculations(systemId)
  const database = useSystem(systemId).data?.value.database.name ?? ''
  const last = latestOf(calculations.data?.value ?? [])
  return (
    <>
      <Button size="sm" aria-label={NEW_CALCULATION} onClick={() => go(paths.results(systemId, 'setup', ''))}>
        <Play className="size-3.5" /> {NEW_CALCULATION}
      </Button>
      {last === undefined ? null : (
        <IconButton label={runAgainLabel(last, database)} onClick={() => startImpact('impact', `?call=${last.id}`)}>
          <RotateCw />
        </IconButton>
      )}
    </>
  )
}
