import { useState } from 'react'
import type { Call } from '@/api/types'
import { chosenRefs } from './chosen'
import { folded } from './fold'
import { TrailItem } from './TrailItem'

function Run({ tool, calls, at, trail }: { tool: string; calls: Call[]; at: number; trail: Call[] }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="py-0.5">
      <button type="button" aria-expanded={open} className="flex items-baseline gap-2 text-left hover:underline" onClick={() => setOpen(!open)}>
        <span className="font-medium">{tool}</span>
        <span className="text-muted-foreground">×{calls.length}</span>
      </button>
      {open ? (
        <ul className="pl-3">
          {calls.map((call, offset) => (
            <TrailItem key={call.id} call={call} chosen={chosenRefs(trail, at + offset)} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export function Trail({ calls }: { calls: Call[] }) {
  return (
    <ul className="flex flex-col text-xs">
      {folded(calls).map((part) =>
        part.kind === 'call' ? (
          <TrailItem key={part.call.id} call={part.call} chosen={chosenRefs(calls, part.at)} />
        ) : (
          <Run key={part.calls[0].id} tool={part.tool} calls={part.calls} at={part.at} trail={calls} />
        ),
      )}
    </ul>
  )
}
