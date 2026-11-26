import { useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { ResultBand } from '@/editors/results/ResultBand'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { NARROW_BELOW } from './inspector'
import { ResizeEdge } from './ResizeEdge'
import { resizeResult, WIDEST_SHARE } from './resize'
import { useMinWidth } from './useMinWidth'

/**
 * The open result beside the graph: a drawer at the right, two thirds of the window wide with the graph still
 * shown beside it, whose left border is dragged to a width it keeps, and the whole area under the band below
 * 768 px.
 */
export function ResultDrawer({ systemId }: { systemId: string }) {
  const narrow = !useMinWidth(NARROW_BELOW)
  const kept = useUi((s) => s.resultWidth)
  const panel = useRef<HTMLElement>(null)
  const held = useRef(() => panel.current)
  const [dragged, setDragged] = useState<number | null>(null)
  const width = dragged ?? kept
  return (
    <section
      ref={panel}
      aria-label="Result"
      data-clear={narrow ? undefined : 'right'}
      style={narrow ? undefined : { maxWidth: `${WIDEST_SHARE * 100}vw`, ...(width === null ? {} : { width: `${width}px` }) }}
      className={cn(
        'relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-background shadow-lg',
        narrow
          ? 'col-span-2 col-start-1 row-span-2 row-start-2'
          : cn('col-start-3 row-span-2 row-start-2 justify-self-end', width === null && 'w-[min(68vw,calc(100vw-380px))]'),
      )}
    >
      {narrow ? null : <ResizeEdge label="Resize the result drawer" panel={held.current} width={width} onDrag={setDragged} onDrop={resizeResult} onReset={() => resizeResult(null)} />}
      {narrow ? (
        <div className="flex flex-wrap items-center gap-1 border-b p-1">
          <ResultBand systemId={systemId} />
        </div>
      ) : null}
      <div className="@container min-h-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </section>
  )
}
