import { memo } from 'react'
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react'
import { routePath } from './layout'

export interface EdgeText {
  x: number
  y: number
  width: number
  height: number
  text: string
}

export interface FlowEdgeData extends Record<string, unknown> {
  amount: number
  unit: string
  formula: string | null
  points: [number, number][] | null
  rest: boolean
  label: EdgeText | null
}

export type FlowEdgeType = Edge<FlowEdgeData, 'flow'>

function FlowEdgeComponent({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd }: EdgeProps<FlowEdgeType>) {
  const points = data?.points ?? null
  const path =
    data?.rest === true && points !== null
      ? routePath(points)
      : getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 0 })[0]
  const label = data?.rest === true ? (data.label ?? null) : null
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={data?.amount === 0 ? { strokeDasharray: '6 4' } : undefined} />
      {label === null ? null : (
        <EdgeLabelRenderer>
          <div
            data-testid="edge-label"
            style={{ position: 'absolute', transform: `translate(${label.x}px, ${label.y}px)`, width: label.width, height: label.height }}
            className="nodrag nopan pointer-events-none whitespace-nowrap text-right text-xs leading-none text-muted-foreground"
          >
            {label.text}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

export const FlowEdge = memo(FlowEdgeComponent)
