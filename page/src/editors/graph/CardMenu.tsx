import { NodeToolbar, Position, useInternalNode, useNodeId, useStore } from '@xyflow/react'
import { useLayoutEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import type { Process } from '@/api/types'
import { isActivityPath, paths, processOfPath, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useClearance } from '@/window/clearance'
import { DetailLink } from '@/window/DetailLink'
import { openInspector, useInspectorShown } from '@/window/inspector'
import { runCanvas } from '@/window/shortcuts'
import { clearArea, POINTER_WIDTH, TOOLBAR_OFFSET, toolbarFor, type Size, type ToolbarSide } from './layout'

const ITEM = 'nodrag nopan whitespace-nowrap rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'

function Pointer({ side, at }: { side: ToolbarSide; at: number }) {
  return (
    <span
      aria-hidden
      data-pointer={side}
      style={{ left: at - POINTER_WIDTH / 2 }}
      className={cn(
        'pointer-events-none absolute h-0 w-0 border-x-[5px] border-x-transparent',
        side === 'top' ? '-bottom-1.5 border-t-[6px] border-t-muted-foreground/55' : '-top-1.5 border-b-[6px] border-b-muted-foreground/55',
      )}
    />
  )
}

/** A card's menu, drawn while the card is the one shown: the process chosen, or the linked system a click selected. */
export function CardToolbar({ size, shown, children }: { size: Size; shown: boolean; children: ReactNode }) {
  const [row, setRow] = useState<HTMLDivElement | null>(null)
  const [natural, setNatural] = useState<Size | null>(null)
  const [rowHeight, setRowHeight] = useState<number | null>(null)
  const id = useNodeId()
  const node = useInternalNode(id ?? '')
  const panX = useStore((s) => s.transform[0])
  const panY = useStore((s) => s.transform[1])
  const zoom = useStore((s) => s.transform[2])
  const canvasWidth = useStore((s) => s.width)
  const canvasHeight = useStore((s) => s.height)
  const clearance = useClearance((s) => s.clearance)
  useLayoutEffect(() => {
    if (row === null || natural !== null) return
    const box = row.getBoundingClientRect()
    if (box.width === 0) return
    setNatural({ width: box.width, height: box.height })
    setRowHeight(box.height)
  }, [row, natural])
  const left = node === undefined ? 0 : node.internals.positionAbsolute.x * zoom + panX
  const top = node === undefined ? 0 : node.internals.positionAbsolute.y * zoom + panY
  const placed =
    natural === null || rowHeight === null || node === undefined
      ? null
      : toolbarFor({
          card: { x: left, y: top, width: size.width * zoom, height: size.height * zoom },
          natural,
          height: rowHeight,
          clear: clearArea({ width: canvasWidth, height: canvasHeight }, clearance),
        })
  useLayoutEffect(() => {
    if (row === null) return
    const measured = row.getBoundingClientRect().height
    if (measured > 0 && measured !== rowHeight) setRowHeight(measured)
  }, [row, rowHeight, placed?.width])
  return (
    <NodeToolbar
      isVisible={shown}
      position={placed?.side === 'bottom' ? Position.Bottom : Position.Top}
      align="start"
      offset={TOOLBAR_OFFSET}
      style={placed === null ? undefined : { translate: `${placed.left - left}px 0px` }}
    >
      <div ref={setRow} role="toolbar" aria-label="Card" style={placed?.width == null ? undefined : { width: placed.width }} className="relative inline-flex flex-wrap items-center gap-0.5 rounded-xl border bg-chrome/95 p-1 shadow-lg">
        {placed === null ? null : <Pointer side={placed.side} at={placed.pointer} />}
        {children}
      </div>
    </NodeToolbar>
  )
}

export function ProcessMenuItems({ systemId, process }: { systemId: string; process: Process }) {
  const go = useGo()
  const { pathname } = useLocation()
  const shown = useInspectorShown()
  const chosen = useUi((s) => s.chosenProcess)
  const here = processOfPath(pathname)
  const onDetails = here !== null && here.systemId === systemId && here.code === process.code
  const onActivity = isActivityPath(pathname, systemId) && chosen === process.id
  return (
    <>
      {shown && onDetails ? null : (
        <DetailLink to={onDetails ? pathname : paths.process(systemId, process.code)} className={ITEM}>
          Open details
        </DetailLink>
      )}
      {shown && onActivity ? null : (
        <button
          type="button"
          className={ITEM}
          onClick={() => {
            useUi.getState().chooseProcess(process.id)
            go(paths.system(systemId))
            openInspector()
          }}
        >
          Show process activity
        </button>
      )}
      <button type="button" className={ITEM} onClick={() => runCanvas({ show: process.code })}>
        Center card
      </button>
      <button type="button" className={ITEM} onClick={() => useRequestDialog.getState().open({ systemId, entity: 'process', entityId: process.id })}>
        Request a change
      </button>
    </>
  )
}

export function LinkedMenuItems({ to, node }: { to: string; node: string }) {
  return (
    <>
      <AppLink to={to} className={ITEM}>
        Open
      </AppLink>
      <button type="button" className={ITEM} onClick={() => runCanvas({ show: node })}>
        Center card
      </button>
    </>
  )
}
