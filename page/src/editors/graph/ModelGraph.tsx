import { Background, Controls, MiniMap, Panel, ReactFlow, ReactFlowProvider, applyNodeChanges, useNodesInitialized, useReactFlow, useStore, type Edge, type NodeChange, type NodeTypes, type EdgeTypes, type FitViewOptions } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Ellipsis, LocateFixed, Maximize } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLayout, usePlaceCards, useReleaseCards, useSystemAs } from '@/api/queries'
import type { LogEntry, ProductSystem } from '@/api/types'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/utils'
import { ICON_BUTTON, IconButton } from '@/window/IconButton'
import { useMinWidth } from '@/window/useMinWidth'
import { useWidth } from '@/window/useWidth'
import { CANVAS_EVENT, keysOf, type CanvasCommand } from '@/window/shortcuts'
import { buildGraph, changedCards, changedSuppliers, droppedCards, edgeText, hotFrom, type GraphNode, type Outlines } from './build'
import { FlowEdge, type FlowEdgeData } from './FlowEdge'
import { atRest, framing } from './layout'
import { LinkedNode } from './LinkedNode'
import { ProcessNode } from './ProcessNode'

const nodeTypes: NodeTypes = { process: ProcessNode, linked: LinkedNode }
const edgeTypes: EdgeTypes = { flow: FlowEdge }

interface GraphProps {
  system: ProductSystem
  latest: LogEntry | null
  outlines?: Outlines
  calculate?: ReactNode
}

const MOVE = { duration: 250 }
const QUIET_MS = 10_000
const MINIMAP_LANE = 446
const TOOLBAR_FLOOR = 360
const PANEL_MARGIN = 15
const LIFT = 158

function Graph({ system, latest, outlines, calculate }: GraphProps) {
  const flow = useReactFlow<GraphNode>()
  const theme = useUi((s) => s.theme)
  const chooseProcess = useUi((s) => s.chooseProcess)
  const reference = system.reference_process
  const [variant, setVariant] = useState<string | null>(null)
  const formulaValues = useUi((s) => s.formulaValues)
  const setFormulaValues = useUi((s) => s.setFormulaValues)
  const scaledView = useUi((s) => s.scaledView)
  const setScaledView = useUi((s) => s.setScaledView)
  const wide = useMinWidth(1024)
  const chosenMinimap = useUi((s) => s.minimapOpen)
  const setMinimapOpen = useUi((s) => s.setMinimapOpen)
  const minimap = chosenMinimap ?? wide
  const frame = useRef<HTMLDivElement>(null)
  const canvasWidth = useWidth(frame)
  const lifted = minimap && canvasWidth > 0 && canvasWidth < MINIMAP_LANE + TOOLBAR_FLOOR
  const asVariant = useSystemAs(system.id, variant)
  const drawn = variant !== null && asVariant.data ? asVariant.data.value : system
  const built = useMemo(() => buildGraph(drawn, hotFrom(latest), reference, outlines), [drawn, latest, reference, outlines])
  const layout = useLayout(system.id, variant)
  const place = usePlaceCards(system.id, variant)
  const placed = useMemo(() => new Map((layout.data?.value.cards ?? []).map((p) => [p.code, p])), [layout.data])
  const routes = useMemo(() => new Map((layout.data?.value.edges ?? []).map((r) => [`flow-${r.exchange_id}`, r])), [layout.data])
  const scaling = layout.data?.value.scaling ?? null
  const scaledAvailable = scaling === null
  const scaledShown = scaledView && scaledAvailable
  const [nodes, setNodes] = useState<GraphNode[]>([])
  useEffect(() => {
    setNodes(
      built.nodes.flatMap((node): GraphNode[] => {
        const spot = placed.get(node.id)
        return spot === undefined ? [] : [{ ...node, position: { x: spot.x, y: spot.y }, data: { ...node.data, placement: { ...spot, scaled: scaledShown ? spot.scaled : null } } } as GraphNode]
      }),
    )
  }, [built, placed, scaledShown])
  const edges = useMemo((): Edge[] => {
    const positions = new Map(nodes.map((node) => [node.id, node.position]))
    return built.edges.map((edge) => {
      const route = routes.get(edge.id)
      const label = route === undefined ? null : edgeText(route.label, scaledShown, formulaValues)
      return { ...edge, data: { ...(edge.data as FlowEdgeData), points: route?.points ?? null, label, rest: atRest(edge.source, edge.target, placed, positions) } }
    })
  }, [built.edges, routes, placed, nodes, scaledShown, formulaValues])
  const onNodesChange = (changes: NodeChange<GraphNode>[]) => {
    setNodes((current) => {
      const next = applyNodeChanges(changes, current)
      const dropped = droppedCards(changes, next)
      if (dropped.length > 0) place.mutate(dropped)
      return next
    })
  }
  const dock = useRef<HTMLDivElement>(null)
  const clear = useCallback((): FitViewOptions['padding'] => ({ top: '5%', right: '5%', bottom: `${(dock.current?.offsetHeight ?? 0) + 24 + (lifted ? LIFT : 0)}px`, left: '5%' }), [lifted])
  const [following, setFollowing] = useState(true)
  const pause = useCallback(() => setFollowing(false), [])
  useEffect(() => setFollowing(true), [system.id])
  const fit = useCallback(() => {
    if (following) void flow.fitView({ ...MOVE, maxZoom: 1, padding: clear() })
    else setFollowing(true)
  }, [following, flow, clear])
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
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)
  const fittedFor = useRef<string | null>(null)
  const measured = useNodesInitialized()
  const arrangement = layout.data
  useEffect(() => {
    if (!following || !measured || nodes.length === 0) return
    const first = fittedFor.current !== system.id
    const frame = window.requestAnimationFrame(() => {
      fittedFor.current = system.id
      const both = [...changed, ...suppliers]
      const chosen = building && changed.length > 0 ? framing(flow.getNodesBounds(changed), flow.getNodesBounds(both), { width, height }) : 'whole'
      if (chosen === 'whole') void flow.fitView({ ...(first ? {} : MOVE), maxZoom: 1, padding: clear() })
      else void flow.fitView({ ...MOVE, nodes: (chosen === 'suppliers' ? both : changed).map((id) => ({ id })), maxZoom: 1, padding: clear() })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [following, measured, arrangement, nodes.length, system.id, flow, clear, building, changed, suppliers, width, height])
  const focus = useCallback(() => {
    if (reference === null) return
    pause()
    void flow.fitView({ ...MOVE, nodes: [{ id: reference }], maxZoom: 1, padding: 0.4 })
  }, [flow, reference, pause])
  const reorganise = useCallback(() => void layout.refetch(), [layout])
  const show = useCallback(
    (code: string) => {
      const spot = placed.get(code)
      if (spot === undefined) return
      pause()
      void flow.setCenter(spot.x + spot.width / 2, spot.y + spot.height / 2, { ...MOVE, zoom: flow.getZoom() })
    },
    [placed, flow, pause],
  )
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
  const release = useReleaseCards(system.id)
  const chosenSeq = useUi((s) => (s.chosenEntry?.systemId === system.id ? s.chosenEntry.seq : null))
  useEffect(() => {
    if (chosenSeq === null || latest?.seq !== chosenSeq) return
    const cards = changedCards(built.nodes)
    if (cards.length === 0) return
    pause()
    void flow.fitView({ ...MOVE, nodes: cards.map((id) => ({ id })), maxZoom: 1, padding: 0.3 })
  }, [chosenSeq, latest, built.nodes, flow, pause])
  const notes = [
    ...(scaling === null ? [] : [scaling]),
    ...(asVariant.error ? [asVariant.error.message] : []),
    ...(layout.error && !asVariant.error ? [layout.error.message] : []),
  ]
  return (
    <div ref={frame} className="relative h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => (node.type === 'process' ? chooseProcess(node.data.process.id) : undefined)}
        onPaneClick={() => chooseProcess(null)}
        onMoveStart={(event) => (event === null ? undefined : pause())}
        onNodeDragStart={pause}
        nodesConnectable={false}
        colorMode={theme === 'ecosemantic' ? 'dark' : 'light'}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
      >
        <Panel
          position="bottom-center"
          className={cn('w-max', minimap && !lifted ? 'max-w-[calc(100%-446px)]' : 'max-w-[calc(100%-1rem)]')}
          style={lifted ? { marginBottom: PANEL_MARGIN + LIFT } : undefined}
        >
          <div ref={dock} className="flex max-w-full flex-col items-center gap-1">
            {notes.length > 0 ? (
              <p role="status" className="max-w-full rounded-md bg-chrome/95 px-2 py-0.5 text-center text-xs shadow">
                {notes.map((note) => (
                  <span key={note} className="block">
                    {note}
                  </span>
                ))}
              </p>
            ) : null}
            <div
              role="toolbar"
              aria-label="Canvas"
              className="flex max-w-full flex-wrap items-center justify-center gap-1 rounded-xl border bg-chrome/95 p-1 shadow-lg backdrop-blur"
            >
              {calculate ? (
                <>
                  {calculate}
                  <span className="mx-0.5 h-5 w-px bg-border" />
                </>
              ) : null}
              <label className="flex min-w-0 items-center gap-1 px-1 text-xs">
                State
                <select
                  aria-label="State"
                  className="nodrag min-w-28 max-w-48 rounded-sm border bg-background px-1"
                  value={variant ?? ''}
                  onChange={(e) => setVariant(e.target.value === '' ? null : e.target.value)}
                >
                  <option value="">base values</option>
                  {system.cases.map((c) => (
                    <option key={`case:${c.name}`} value={c.name}>
                      case {c.name}
                    </option>
                  ))}
                  {system.scenarios.map((sc) => (
                    <option key={`scenario:${sc.name}`} value={sc.name}>
                      scenario {sc.name}
                    </option>
                  ))}
                </select>
              </label>
              <span className="mx-0.5 h-5 w-px bg-border" />
              <IconButton label="Fit the graph" shortcut="fit" side="top" onClick={fit}>
                <Maximize />
              </IconButton>
              {following ? null : (
                <Button size="sm" variant="ghost" onClick={fit}>
                  <LocateFixed className="size-3.5" /> Follow the build
                </Button>
              )}
              <DropdownMenu>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuTrigger aria-label="More canvas options" className={ICON_BUTTON}>
                      <Ellipsis />
                    </DropdownMenuTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="top" sideOffset={6}>
                    More canvas options
                  </TooltipContent>
                </Tooltip>
                <DropdownMenuContent side="top" align="end" className="w-64">
                  <DropdownMenuCheckboxItem
                    checked={scaledShown}
                    disabled={!scaledAvailable}
                    onCheckedChange={(on) => setScaledView(on === true)}
                    className="flex-wrap"
                  >
                    Scaled to 1 unit
                    {scaling === null ? null : <span className="basis-full text-xs text-muted-foreground">{scaling}</span>}
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem checked={formulaValues} onCheckedChange={(on) => setFormulaValues(on === true)}>
                    Formula values
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuCheckboxItem checked={minimap} onCheckedChange={(on) => setMinimapOpen(on === true)}>
                    Minimap
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={focus}>
                    Focus the reference process
                    <DropdownMenuShortcut>{keysOf('focus')}</DropdownMenuShortcut>
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={reorganise}>
                    Reorganise the graph
                    <DropdownMenuShortcut>{keysOf('reorganise')}</DropdownMenuShortcut>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => {
                      release.mutate()
                      setFollowing(true)
                    }}
                  >
                    Reset layout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </Panel>
        {layout.data && built.nodes.length === 0 ? (
          <Panel position="top-center">
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
          </Panel>
        ) : null}
        <Background />
        <Controls showInteractive={false} showFitView={false} onZoomIn={pause} onZoomOut={pause} />
        {minimap ? <MiniMap pannable zoomable /> : null}
      </ReactFlow>
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
