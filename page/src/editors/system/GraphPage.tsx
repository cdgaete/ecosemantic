import { useMemo } from 'react'
import { colourOfEntry } from '@/activity/agents'
import { useLog } from '@/api/queries'
import { useLive } from '@/api/stream'
import { outlinesFrom, ownParts } from '@/editors/graph/build'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { ResultBand } from '@/editors/results/ResultBand'
import { useBand } from '@/editors/results/useBand'
import { useUi } from '@/store/ui'
import type { SystemView } from './SystemEditor'

export function GraphPage({ view }: { view: SystemView }) {
  const log = useLog(view.id)
  const live = useLive((s) => s.latest[view.id] ?? null)
  const latest = view.version ? null : (live ?? log.data?.value.at(-1) ?? null)
  const chosen = useUi((s) => s.chosenEntry)
  const since = useUi((s) => s.since[view.id])
  const marked = chosen !== null && chosen.systemId === view.id ? (log.data?.value.find((entry) => entry.seq === chosen.seq) ?? null) : latest
  const outlines = useMemo(() => {
    const fresh = since === undefined ? [] : (log.data?.value ?? []).filter((entry) => entry.seq > since)
    return outlinesFrom(view.system, [...fresh, ...(marked ? [marked] : [])], colourOfEntry)
  }, [view.system, log.data, since, marked])
  const calculate = view.version === null ? <ResultBand systemId={view.id} /> : undefined
  const band = useBand(view.id, view.version === null)
  const split = band?.split
  const owns = useMemo(() => ownParts(split), [split])
  return <ModelGraph system={view.system} latest={marked} outlines={outlines} owns={view.version === null ? owns : undefined} split={view.version === null ? split : undefined} calculate={calculate} />
}
