import { Handle, Position, useStore, type NodeProps } from '@xyflow/react'
import { memo } from 'react'
import { useSystems } from '@/api/queries'
import { formatAmount, shortHash } from '@/lib/format'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { cn } from '@/lib/utils'
import { Icon } from '@/window/Icon'
import type { LinkedNodeType } from './build'
import { detailAt } from './layout'

function LinkedNodeComponent({ data }: NodeProps<LinkedNodeType>) {
  const systems = useSystems()
  const name = systems.data?.value.find((s) => s.id === data.productSystemId)?.name ?? data.productSystemId
  const detail = useStore((s) => detailAt(s.transform[2]))
  const output = data.placement.scaled === null ? undefined : Object.values(data.placement.scaled)[0]
  const target = data.atHash === null ? paths.system(data.productSystemId) : paths.version(data.productSystemId, data.atHash)
  return (
    <div style={{ height: data.placement.height }} className="w-[300px] overflow-hidden rounded-xl outline outline-[1.5px] -outline-offset-[1.5px] outline-dashed outline-node-border bg-muted/40 text-xs shadow-sm">
      <Handle type="source" position={Position.Right} id="out" style={{ top: data.placement.output }} className="!bg-link-stroke" />
      <div className={cn('flex h-[40px] gap-2 overflow-hidden px-3 font-semibold leading-snug', detail === 'rows' ? 'items-start py-1' : 'items-center text-2xl')}>
        <Icon name="system" />
        <AppLink to={target} title={name} className="line-clamp-2 min-w-0 break-words hover:underline nodrag nopan">
          {name}
        </AppLink>
      </div>
      {detail === 'rows' ? (
        <div className="flex h-[34px] items-center gap-2 px-3 py-[6px] text-muted-foreground shadow-[inset_0_1px_0_rgb(var(--node-border))]">
          <span className="font-mono">{shortHash(data.atHash)}</span>
          <span>{data.case === null ? 'base values' : `case ${data.case}`}</span>
          {output === undefined ? null : <span className="ml-auto tabular-nums text-foreground">{formatAmount(output)}</span>}
        </div>
      ) : null}
    </div>
  )
}

export const LinkedNode = memo(LinkedNodeComponent)
