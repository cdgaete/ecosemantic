import { BaseEdge, EdgeLabelRenderer, Handle, Position, getStraightPath, type EdgeProps, type NodeProps } from '@xyflow/react'
import { memo } from 'react'
import type { StageNodeType } from './build'

function StageBoxComponent({ data, width, height }: NodeProps<StageNodeType>) {
  return (
    <div
      data-stage={data.stage}
      style={{ width, height, backgroundColor: data.fill, borderColor: data.line }}
      className="pointer-events-none relative overflow-hidden rounded-xl border-[1.5px]"
    >
      <Handle id="in" type="target" position={Position.Left} isConnectable={false} className="!size-0 !border-0 !opacity-0" />
      <Handle id="out" type="source" position={Position.Right} isConnectable={false} className="!size-0 !border-0 !opacity-0" />
    </div>
  )
}

function StageTabsComponent({ boxes }: { boxes: StageNodeType[] }) {
  return (
    <EdgeLabelRenderer>
      {boxes.map((box) => (
        <span
          key={box.id}
          data-stage-tab={box.data.stage}
          style={{ position: 'absolute', left: 0, top: 0, maxWidth: box.width, transform: `translate(${box.position.x}px, ${box.position.y}px)`, backgroundColor: box.data.colour }}
          className="pointer-events-none rounded-tl-xl rounded-r-md px-2 py-0.5 text-xs font-semibold text-background"
        >
          {box.data.label}
        </span>
      ))}
    </EdgeLabelRenderer>
  )
}

function TetherEdgeComponent({ id, style, sourceX, sourceY, targetX, targetY }: EdgeProps) {
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  return <BaseEdge id={id} path={path} style={style} interactionWidth={0} />
}

export const StageBox = memo(StageBoxComponent)

export const StageTabs = memo(StageTabsComponent)

export const TetherEdge = memo(TetherEdgeComponent)
