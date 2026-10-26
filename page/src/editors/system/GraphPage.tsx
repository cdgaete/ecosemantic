import { Play } from 'lucide-react'
import { useMemo } from 'react'
import { colourOfEntry } from '@/activity/agents'
import { useLog } from '@/api/queries'
import { useLive } from '@/api/stream'
import { Button } from '@/components/ui/button'
import { outlinesFrom } from '@/editors/graph/build'
import { ModelGraph } from '@/editors/graph/ModelGraph'
import { paths, useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'
import type { SystemView } from './SystemEditor'

export function GraphPage({ view }: { view: SystemView }) {
  const log = useLog(view.id)
  const live = useLive((s) => s.latest[view.id] ?? null)
  const go = useGo()
  const latest = view.version ? null : (live ?? log.data?.value.at(-1) ?? null)
  const chosen = useUi((s) => s.chosenEntry)
  const since = useUi((s) => s.since[view.id])
  const marked = chosen !== null && chosen.systemId === view.id ? (log.data?.value.find((entry) => entry.seq === chosen.seq) ?? null) : latest
  const outlines = useMemo(() => {
    const fresh = since === undefined ? [] : (log.data?.value ?? []).filter((entry) => entry.seq > since)
    return outlinesFrom(view.system, [...fresh, ...(marked ? [marked] : [])], colourOfEntry)
  }, [view.system, log.data, since, marked])
  const calculate =
    view.version === null ? (
      <Button size="sm" aria-label="Calculate an impact result" onClick={() => go(paths.results(view.id, 'setup', ''))}>
        <Play className="size-3.5" /> Calculate
      </Button>
    ) : undefined
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 border-t">
        <ModelGraph system={view.system} latest={marked} outlines={outlines} calculate={calculate} />
      </div>
      <p className="px-4 py-1 text-xs text-muted-foreground">One column per step away from the functional unit, which sits at the right. The outlined card is what the latest entry changed; a flashing value was edited. Drag a card to keep its place.</p>
    </div>
  )
}
