import { Background, MiniMap, MiniMapNode, ReactFlow, ReactFlowProvider, applyNodeChanges, useNodesInitialized, useReactFlow, useStore, type Edge, type MiniMapNodeProps, type NodeChange, type NodeTypes, type EdgeTypes } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useLayout, usePlaceCards, useReleaseCards, useSystemAs } from '@/api/queries'
import type { Arrangement, ContributionResult, LogEntry, ProductSystem } from '@/api/types'
import { paths, processOfPath, useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { ISLAND_GAP, useClearance, type Clearance } from '@/window/clearance'
import { useSheetTop } from '@/window/cover'
import { dismissInspector, openInspector } from '@/window/inspector'
import { dockedOf, useLeaveSheet } from '@/window/sheets'
import { InSlot } from '@/window/slots'
import { ToolsGrip } from '@/window/ToolsGrip'
import { CANVAS_EVENT, type CanvasCommand } from '@/window/shortcuts'
import { useCanvasVariant } from '@/window/useCanvasState'
import { useMinWidth } from '@/window/useMinWidth'
import { buildGraph, changedCards, changedSuppliers, droppedCards, edgeText, hotFrom, stageNodes, tetherEdges, STAGE_PREFIX, type GraphNode, type Outlines, type OwnShown, type Supplies } from './build'
import { CanvasToolbar } from './CanvasToolbar'
import { FlowEdge, type FlowEdgeData } from './FlowEdge'
import { atRest, clearArea, clearCentre, detailAt, framing, READABLE_ZOOM, revealFor, viewportFor, type Bounds, type Point, type Viewport, type ZoomLimits } from './layout'
import { LinkedNode } from './LinkedNode'
import { ProcessNode } from './ProcessNode'
import { StageBox, StageTabs, TetherEdge } from './StageBox'
import { ViewTools } from './ViewTools'

const nodeTypes: NodeTypes = { process: ProcessNode, linked: LinkedNode, stage: StageBox }
const edgeTypes: EdgeTypes = { flow: FlowEdge, tether: TetherEdge }

interface GraphProps {
  system: ProductSystem
  latest: LogEntry | null
  outlines?: Outlines
  owns?: Map<string, OwnShown>
  split?: ContributionResult
  calculate?: ReactNode
}

const MOVE = { duration: 250 }
const TAP_SLOP = 4
const HANDLES_CLICK = 'a, button, input, select, textarea, [role="button"], [role="slider"]'
const QUIET_MS = 10_000
const ZOOM = { min: 0.2, max: 1 }
const READABLE = { min: READABLE_ZOOM, max: ZOOM.max }

function minimapCard({ id, ...rest }: MiniMapNodeProps) {
  return id.startsWith(STAGE_PREFIX) ? null : <MiniMapNode id={id} {...rest} />
}

/** The box a drawn card's title takes on screen, or null while the card is drawn without one. */
function titleBox(frame: HTMLElement | null, code: string): DOMRect | null {
  const card = Array.from(frame?.querySelectorAll<HTMLElement>('.react-flow__node') ?? []).find((node) => node.dataset.id === code)
  const box = card?.querySelector<HTMLElement>('[data-title]')?.getBoundingClientRect()
  return box !== undefined && box.width > 0 && box.height > 0 ? box : null
}

function Graph({ system, latest, outlines, owns, split, calculate }: GraphProps) {
  const flow = useReactFlow<GraphNode>()
  const theme = useUi((s) => s.theme)
  const chooseProcess = useUi((s) => s.chooseProcess)
  const location = useLocation()
  const go = useGo()
  const reference = system.reference_process
  const variant = useCanvasVariant(system)?.name ?? null
  const formulaValues = useUi((s) => s.formulaValues)
  const scaledView = useUi((s) => s.scaledView)
  const wide = useMinWidth(1024)
  const chosenMinimap = useUi((s) => s.minimapOpen)
  const setMinimapOpen = useUi((s) => s.setMinimapOpen)
  const minimap = chosenMinimap ?? wide
  const narrow = !useMinWidth(768)
  const frame = useRef<HTMLDivElement>(null)
  const clearance = useClearance((s) => s.clearance)
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)
  const asVariant = useSystemAs(system.id, variant)
  const drawn = variant !== null && asVariant.data ? asVariant.data.value : system
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set<string>())
  const processCodes = useMemo(() => new Set(drawn.processes.map((p) => p.code)), [drawn])
  const shown = useMemo(
    () => [...expanded].filter((code) => processCodes.has(code)).sort(),
    [expanded, processCodes],
  )
  const layout = useLayout(system.id, variant, shown)
  const place = usePlaceCards(system.id, variant, shown)
  const arranged = layout.data?.value ?? null
  const built = useMemo(
    () => (arranged === null ? { nodes: [], edges: [] } : buildGraph(drawn, arranged, hotFrom(latest), reference, outlines)),
    [drawn, arranged, latest, reference, outlines],
  )
  const placed = useMemo(() => new Map((arranged?.cards ?? []).map((p) => [p.code, p])), [arranged])
  const routes = useMemo(() => new Map((arranged?.edges ?? []).map((r) => [`flow-${r.exchange_id}`, r])), [arranged])
  const scaling = arranged?.scaling ?? null
  const scaledAvailable = scaling === null
  const scaledShown = scaledView && scaledAvailable
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const boxes = useMemo(() => (arranged === null ? [] : stageNodes(arranged.stages, split)), [arranged, split])
  const supplies = useMemo(
    () => new Map<string, Supplies>((arranged?.shared_suppliers ?? []).map((one) => [one.code, { processes: one.processes, stages: one.stages }])),
    [arranged],
  )
  const toggleRows = useCallback((code: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }, [])
  const drawnNodes = useCallback(
    (arrangement: Arrangement): GraphNode[] => [
      ...boxes,
      ...built.nodes.flatMap((node): GraphNode[] => {
        const spot = placed.get(node.id)
        if (spot === undefined) return []
        const data = { ...node.data, placement: { ...spot, scaled: scaledShown ? spot.scaled : null }, card: arrangement.card }
        return [{ ...node, position: { x: spot.x, y: spot.y }, data: node.type === 'process' ? { ...data, own: owns?.get(node.id) ?? null, supplies: supplies.get(node.id) ?? null, rows: { expanded: expanded.has(node.id), toggle: toggleRows } } : data } as GraphNode]
      }),
    ],
    [built.nodes, boxes, placed, scaledShown, owns, supplies, expanded, toggleRows],
  )
  useEffect(() => {
    if (arranged === null) return
    setNodes(drawnNodes(arranged))
  }, [drawnNodes, arranged])
  const edges = useMemo((): Edge[] => {
    const positions = new Map(nodes.map((node) => [node.id, node.position]))
    const flows = built.edges.map((edge) => {
      const route = routes.get(edge.id)
      const label = route === undefined ? null : edgeText(route.label, scaledShown, formulaValues)
      return { ...edge, data: { ...(edge.data as FlowEdgeData), points: route?.points ?? null, label, rest: atRest(edge.source, edge.target, placed, positions) } }
    })
    return [...(arranged === null ? [] : tetherEdges(arranged.stages)), ...flows]
  }, [built.edges, routes, placed, nodes, scaledShown, formulaValues, arranged])
  const onNodesChange = (changes: NodeChange<GraphNode>[]) => {
    setNodes((current) => {
      const next = applyNodeChanges(changes, current)
      const dropped = droppedCards(changes, next)
      if (dropped.length > 0)
        place.mutate(dropped, {
          onError: () => {
            if (arranged !== null) setNodes(drawnNodes(arranged))
          },
        })
      return next
    })
  }
  const [following, setFollowing] = useState(true)
  const overview = useRef(false)
  const pause = useCallback(() => {
    overview.current = false
    setFollowing(false)
  }, [])
  useEffect(() => {
    overview.current = false
    setFollowing(true)
  }, [system.id])
  useEffect(() => {
    setExpanded((current) => (current.size === 0 ? current : new Set<string>()))
  }, [system.id])
  const fitOf = useCallback(
    (target: Bounds, anchor: Bounds | null, zoom: ZoomLimits = READABLE): Viewport => viewportFor({ target, anchor, canvas: { width, height }, clearance, zoom }),
    [width, height, clearance],
  )
  const fitAll = useCallback(
    (animate: boolean, zoom: ZoomLimits) => {
      const cards = flow.getNodes().filter((node) => node.type !== 'stage')
      if (cards.length === 0) return
      const target = flow.getNodesBounds(cards)
      const side = reference !== null && cards.some((node) => node.id === reference) ? flow.getNodesBounds([reference]) : null
      void flow.setViewport(fitOf(target, side ?? target, zoom), animate ? MOVE : {})
    },
    [flow, reference, fitOf],
  )
  const fit = useCallback(() => {
    overview.current = true
    if (following) fitAll(true, ZOOM)
    else setFollowing(true)
  }, [following, fitAll])
  const follow = useCallback(() => setFollowing(true), [])
  const seq = latest?.seq ?? null
  const seenSeq = useRef<number | null>(null)
  const [building, setBuilding] = useState(false)
  useEffect(() => {
    seenSeq.current = null
    setBuilding(false)
  }, [system.id])
  useEffect(() => {
    if (seq === null) return
    const before = seenSeq.current
    seenSeq.current = seq
    if (before === null || seq <= before) return
    setBuilding(true)
    const timer = window.setTimeout(() => setBuilding(false), QUIET_MS)
    return () => window.clearTimeout(timer)
  }, [seq])
  const changed = useMemo(() => changedCards(built.nodes), [built.nodes])
  const suppliers = useMemo(() => changedSuppliers(built.edges).filter((code) => !changed.includes(code)), [built.edges, changed])
  const fittedFor = useRef<string | null>(null)
  const measured = useNodesInitialized()
  const arrangement = layout.data
  const sized = useRef<{ width: number; height: number; clearance: Clearance } | null>(null)
  useEffect(() => {
    const before = sized.current
    sized.current = { width, height, clearance }
    if (!measured || nodes.length === 0) return
    if (!following) {
      if (before === null || (before.width === width && before.height === height)) return
      const view = flow.getViewport()
      const from = clearCentre({ width: before.width, height: before.height }, before.clearance)
      const to = clearCentre({ width, height }, clearance)
      void flow.setViewport({ x: view.x + to.x - from.x, y: view.y + to.y - from.y, zoom: view.zoom })
      return
    }
    const first = fittedFor.current !== system.id
    const frame = window.requestAnimationFrame(() => {
      fittedFor.current = system.id
      const both = [...changed, ...suppliers]
      const room = { width: width - clearance.left - clearance.right, height: height - clearance.top - clearance.bottom }
      const chosen = building && changed.length > 0 ? framing(flow.getNodesBounds(changed), flow.getNodesBounds(both), room) : 'whole'
      if (chosen === 'whole') fitAll(!first, overview.current ? ZOOM : READABLE)
      else void flow.setViewport(fitOf(flow.getNodesBounds(chosen === 'suppliers' ? both : changed), null), MOVE)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [following, measured, arrangement, nodes.length, system.id, flow, clearance, building, changed, suppliers, width, height, fitOf, fitAll])
  const focus = useCallback(() => {
    if (reference === null) return
    pause()
    void flow.setViewport(fitOf(flow.getNodesBounds([reference]), null), MOVE)
  }, [flow, reference, pause, fitOf])
  const reorganise = useCallback(() => void layout.refetch(), [layout])
  const show = useCallback(
    (code: string) => {
      const spot = placed.get(code)
      if (spot === undefined) return
      pause()
      const middle = clearCentre({ width, height }, clearance)
      const zoom = flow.getViewport().zoom
      void flow.setViewport({ x: middle.x - (spot.x + spot.width / 2) * zoom, y: middle.y - (spot.y + spot.height / 2) * zoom, zoom }, MOVE)
    },
    [placed, flow, pause, width, height, clearance],
  )
  const sheetOpen = useUi((s) => s.sheetOpen)
  const sheetTop = useSheetTop((s) => s.sheetTop)
  const here = processOfPath(location.pathname)
  const revealedCode = here !== null && here.systemId === system.id ? here.code : null
  const revealKey = narrow && sheetOpen && revealedCode !== null ? `${system.id}:${revealedCode}` : null
  const revealed = useRef<string | null>(null)
  useEffect(() => {
    if (revealKey === null) {
      revealed.current = null
      return
    }
    if (revealed.current === revealKey) return
    const card = arranged?.card
    if (revealedCode === null || sheetTop === null || card === undefined) return
    const spot = placed.get(revealedCode)
    if (spot === undefined) return
    revealed.current = revealKey
    const area = clearArea({ width, height }, clearance)
    const origin = frame.current?.getBoundingClientRect() ?? { left: 0, top: 0 }
    const bottom = Math.min(area.y + area.height, sheetTop - origin.top - ISLAND_GAP)
    const view = flow.getViewport()
    const measured = detailAt(view.zoom) === 'header' ? titleBox(frame.current, revealedCode) : null
    const box =
      measured === null
        ? { x: spot.x, y: spot.y, width: spot.width, height: card.header_height }
        : {
            x: (measured.left - origin.left - view.x) / view.zoom,
            y: (measured.top - origin.top - view.y) / view.zoom,
            width: measured.width / view.zoom,
            height: measured.height / view.zoom,
          }
    const next = revealFor({ box, viewport: view, clear: { ...area, height: bottom - area.y } })
    if (next === null) return
    pause()
    void flow.setViewport(next, MOVE)
  }, [revealKey, revealedCode, arranged, placed, sheetTop, clearance, width, height, flow, pause])
  useEffect(() => {
    const listen = (event: Event) => {
      const command = (event as CustomEvent<CanvasCommand>).detail
      if (typeof command === 'object') show(command.show)
      else if (command === 'fit') fit()
      else if (command === 'focus') focus()
      else reorganise()
    }
    window.addEventListener(CANVAS_EVENT, listen)
    return () => window.removeEventListener(CANVAS_EVENT, listen)
  }, [fit, focus, reorganise, show])
  const leaveSheet = useLeaveSheet()
  const press = useRef<Point | null>(null)
  const dragged = useRef(false)
  const pressAt = (event: ReactPointerEvent<HTMLDivElement>) => {
    press.current = { x: event.clientX, y: event.clientY }
    dragged.current = false
  }
  const moveTo = (event: ReactPointerEvent<HTMLDivElement>) => {
    const from = press.current
    if (from === null || dragged.current) return
    if (Math.hypot(event.clientX - from.x, event.clientY - from.y) > TAP_SLOP) dragged.current = true
  }
  const clickGraph = (event: ReactMouseEvent<HTMLDivElement>) => {
    const target = event.target
    if (dragged.current || (target instanceof Element && target.closest(HANDLES_CLICK) !== null)) return
    leaveSheet()
  }
  const allShown = processCodes.size > 0 && [...processCodes].every((code) => expanded.has(code))
  const someShown = [...processCodes].some((code) => expanded.has(code))
  const setAllRows = useCallback(
    (on: boolean) => setExpanded(on ? new Set(processCodes) : new Set<string>()),
    [processCodes],
  )
  const release = useReleaseCards(system.id, variant, shown)
  const reset = useCallback(() => {
    release.mutate()
    setFollowing(true)
  }, [release, setFollowing])
  const chosenSeq = useUi((s) => (s.chosenEntry?.systemId === system.id ? s.chosenEntry.seq : null))
  useEffect(() => {
    if (chosenSeq === null || latest?.seq !== chosenSeq) return
    const cards = changedCards(built.nodes)
    if (cards.length === 0) return
    pause()
    void flow.setViewport(fitOf(flow.getNodesBounds(cards), null), MOVE)
  }, [chosenSeq, latest, built.nodes, flow, pause, fitOf])
  const notes = [
    ...(scaling === null ? [] : [scaling]),
    ...(asVariant.error ? [asVariant.error.message] : []),
    ...(layout.error && !asVariant.error ? [layout.error.message] : []),
    ...(place.error ? [place.error.message] : []),
  ]
  const started = useRef<Viewport | null>(null)
  const startMove = (event: MouseEvent | TouchEvent | null, at: Viewport) => {
    started.current = event === null ? null : at
  }
  const moveBy = (event: MouseEvent | TouchEvent | null, at: Viewport) => {
    const from = started.current
    if (event === null || from === null) return
    if (from.x === at.x && from.y === at.y && from.zoom === at.zoom) return
    started.current = null
    pause()
  }
  return (
    <div ref={frame} className="relative h-full" onPointerDown={pressAt} onPointerMove={moveTo} onClick={clickGraph}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(event, node) => {
          if (node.type !== 'process') {
            chooseProcess(null)
            return
          }
          const { process, systemId } = node.data
          chooseProcess(process.id)
          if (dockedOf(location.pathname) || (event.target instanceof Element && event.target.closest(HANDLES_CLICK) !== null)) return
          if (here === null || here.systemId !== systemId || here.code !== process.code) go(paths.process(systemId, process.code))
          openInspector()
        }}
        onPaneClick={() => {
          chooseProcess(null)
          dismissInspector(location.pathname)
        }}
        onMoveStart={startMove}
        onMove={moveBy}
        onNodeDragStart={pause}
        nodesConnectable={false}
        colorMode={theme}
        minZoom={ZOOM.min}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <StageTabs boxes={boxes} />
        {minimap ? (
          <InSlot name="minimap">
            <MiniMap
              pannable
              zoomable
              bgColor="rgb(var(--background))"
              maskColor="rgb(var(--muted) / 0.6)"
              maskStrokeColor="rgb(var(--accent))"
              nodeColor="rgb(var(--muted-foreground) / 0.35)"
              nodeStrokeColor="rgb(var(--node-border))"
              nodeComponent={minimapCard}
              className="overflow-hidden rounded-md border shadow-sm"
              style={{ position: 'static', margin: 0 }}
            />
          </InSlot>
        ) : null}
        {layout.data && built.nodes.length === 0 ? (
          <InSlot name="notice">
            <div role="status" className="rounded-xl border bg-chrome/95 px-4 py-3 text-sm shadow-lg">
              <p className="font-semibold">No card to draw</p>
              <p className="text-muted-foreground">This product system holds no process yet, so the layout places nothing.</p>
              {layout.data.value.troubles.length > 0 ? (
                <ul className="list-disc pl-5 text-muted-foreground">
                  {layout.data.value.troubles.map((t, n) => (
                    <li key={`${t.kind}-${n}`}>{t.message}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </InSlot>
        ) : null}
      </ReactFlow>
      <InSlot name="tools">
        <CanvasToolbar
          system={system}
          calculate={narrow ? undefined : calculate}
          grip={narrow ? undefined : <ToolsGrip />}
          notes={notes}
          following={following}
          fit={fit}
          follow={follow}
          scaling={scaling}
          minimap={minimap}
          setMinimapOpen={setMinimapOpen}
          focus={focus}
          reorganise={reorganise}
          reset={reset}
          rowsShown={allShown ? 'all' : someShown ? 'some' : 'none'}
          setAllRows={setAllRows}
        />
      </InSlot>
      <InSlot name="view">
        <ViewTools pause={pause} minimap={minimap} setMinimapOpen={setMinimapOpen} />
      </InSlot>
    </div>
  )
}

export function ModelGraph(props: GraphProps) {
  return (
    <ReactFlowProvider>
      <Graph {...props} />
    </ReactFlowProvider>
  )
}
