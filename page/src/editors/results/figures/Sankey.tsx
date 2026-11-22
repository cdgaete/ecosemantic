import '@xyflow/react/dist/style.css'
import { Background, BaseEdge, ControlButton, Controls, Handle, Position, ReactFlow, ReactFlowProvider, type EdgeProps, type EdgeTypes, type NodeProps, type NodeTypes } from '@xyflow/react'
import { Maximize2 } from 'lucide-react'
import { createContext, useContext, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatAmount, formatShare } from '@/lib/format'
import { stageColour } from '@/lib/stageColours'
import { useUi } from '@/store/ui'
import { Icon } from '@/window/Icon'
import { sankeyElements, type SankeyCard, type SankeyLink, type SankeyLinkDatum, type SankeyNodeDatum } from './sankey'

function pathOf(sx: number, sy: number, ex: number, ey: number): string {
  const mid = (sy + ey) / 2
  return `M${sx},${sy} C${sx},${mid} ${ex},${mid} ${ex},${ey}`
}

function Card({ data }: NodeProps<SankeyCard>) {
  const { datum, unit } = data
  return (
    <div className="h-full rounded-lg border-[1.5px] border-node-border bg-background px-2 py-1 text-xs">
      <Handle type="target" position={Position.Top} isConnectable={false} className="opacity-0" />
      <div className="flex items-center gap-1 truncate border-b border-node-border pb-0.5 font-semibold" title={datum.name}>
        <Icon name="process" />
        {datum.name}
      </div>
      <div className="text-center">
        <b>Upstream total ({formatShare(datum.fraction)})</b>
        <br />
        {formatAmount(datum.score)} {unit}
      </div>
      <Handle type="source" position={Position.Bottom} isConnectable={false} className="opacity-0" />
    </div>
  )
}

const NO_STAGES: string[] = []
const StagesContext = createContext<string[]>(NO_STAGES)

/** The band between two cards, coloured by the stage it hangs under while the split names stages. */
export function Link({ id, sourceX, sourceY, targetX, targetY, data, stages = NO_STAGES }: EdgeProps<SankeyLink> & { stages?: string[] }) {
  const stroke = stages.length === 0 ? 'rgb(var(--link-stroke) / 0.6)' : stageColour(stages, data?.stage ?? null, 0.6)
  return <BaseEdge id={id} path={pathOf(sourceX + (data?.offset ?? 0), sourceY, targetX, targetY)} style={{ stroke, strokeWidth: data?.width }} />
}

function StageLink(props: EdgeProps<SankeyLink>) {
  const stages = useContext(StagesContext)
  return <Link {...props} stages={stages} />
}

const nodeTypes: NodeTypes = { card: Card }
const edgeTypes: EdgeTypes = { link: StageLink }

function Canvas({ elements, drawn, stages, onExpand }: { elements: ReturnType<typeof sankeyElements>; drawn: string; stages: string[]; onExpand?: () => void }) {
  const theme = useUi((s) => s.theme)
  return (
    <ReactFlowProvider>
      <StagesContext.Provider value={stages}>
        <ReactFlow
          key={drawn}
          defaultNodes={elements.nodes}
          defaultEdges={elements.edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ maxZoom: 1, padding: 0.1 }}
          minZoom={0.1}
          maxZoom={2}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          colorMode={theme}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls position="top-right" showInteractive={false}>
            {onExpand ? (
              <ControlButton onClick={onExpand} title="Expand diagram" aria-label="Expand diagram">
                <Maximize2 />
              </ControlButton>
            ) : null}
          </Controls>
        </ReactFlow>
      </StagesContext.Provider>
    </ReactFlowProvider>
  )
}

export function Sankey({ nodes, links, unit, title = '', stages = NO_STAGES }: { nodes: SankeyNodeDatum[]; links: SankeyLinkDatum[]; unit: string; title?: string; stages?: string[] }) {
  const [large, setLarge] = useState(false)
  const elements = useMemo(() => sankeyElements(nodes, links, unit), [nodes, links, unit])
  const drawn = [...nodes.map((node) => `${node.id}:${node.name}:${node.score}:${node.stage ?? ''}`), ...links.map((link) => link.stage ?? '')].join('|')
  return (
    <>
      <figure
        aria-label="Sankey diagram of process contributions, root on top"
        className="max-h-[50vh] min-h-60 w-full overflow-hidden rounded-md border"
        style={{ aspectRatio: `${elements.extent.width} / ${elements.extent.height}` }}
      >
        <Canvas elements={elements} drawn={drawn} stages={stages} onExpand={() => setLarge(true)} />
      </figure>
      <Dialog open={large} onOpenChange={setLarge}>
        <DialogContent aria-describedby={undefined} className="flex h-[90vh] w-[95vw] max-w-[95vw] flex-col gap-2 p-3">
          <DialogHeader className="flex-row items-center justify-between gap-3 space-y-0">
            <DialogTitle className="min-w-0 text-sm">Sankey diagram{title ? ` · ${title}` : ''}</DialogTitle>
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="sm">
                Close
              </Button>
            </DialogClose>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-hidden rounded-md border">{large ? <Canvas elements={elements} drawn={drawn} stages={stages} /> : null}</div>
        </DialogContent>
      </Dialog>
    </>
  )
}
