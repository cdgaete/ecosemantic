import { NodeToolbar, Position, useInternalNode, useNodeId, useStore } from '@xyflow/react'
import { useLayoutEffect, useState, type ReactNode } from 'react'
import type { Process } from '@/api/types'
import { paths, useGo } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { useRequestDialog } from '@/requests/useRequestDialog'
import { useUi } from '@/store/ui'
import { useClearance } from '@/window/clearance'
import { openInspector } from '@/window/inspector'
import { runCanvas } from '@/window/shortcuts'
import { clearArea, TOOLBAR_OFFSET, toolbarFor, type Size } from './layout'

const ITEM = 'nodrag nopan whitespace-nowrap rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:bg-foreground/8 hover:text-foreground'

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
      <div ref={setRow} role="toolbar" aria-label="Card" style={placed?.width == null ? undefined : { width: placed.width }} className="inline-flex flex-wrap items-center gap-0.5 rounded-xl border bg-chrome/95 p-1 shadow-lg">
        {children}
      </div>
    </NodeToolbar>
  )
}

export function ProcessMenuItems({ systemId, process }: { systemId: string; process: Process }) {
  const go = useGo()
  return (
    <>
      <AppLink to={paths.process(systemId, process.code)} className={ITEM}>
        Open details
      </AppLink>
      <button
        type="button"
        className={ITEM}
        onClick={() => {
          useUi.getState().chooseProcess(process.id)
          go(paths.system(systemId))
          openInspector()
        }}
      >
        Filter the log to this process
      </button>
      <button type="button" className={ITEM} onClick={() => runCanvas({ show: process.code })}>
        Focus
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
        Focus
      </button>
    </>
  )
}
