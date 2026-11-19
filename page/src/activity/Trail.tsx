import { useState } from 'react'
import type { Call } from '@/api/types'
import { cn } from '@/lib/utils'
import { chosenRefs } from './chosen'
import { folded, foldedLine } from './fold'
import { TrailItem } from './TrailItem'

function Run({ calls, at, trail }: { calls: Call[]; at: number; trail: Call[] }) {
  const [open, setOpen] = useState(false)
  const failed = calls.some((call) => call.outcome === 'error')
  return (
    <li className="py-0.5">
      <button type="button" aria-expanded={open} className={cn('break-words text-left hover:underline', failed && 'text-destructive')} onClick={() => setOpen(!open)}>
        {foldedLine(calls)}
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

export function Trail({ calls, whole = false }: { calls: Call[]; whole?: boolean }) {
  return (
    <ul className="flex flex-col text-xs">
      {whole
        ? calls.map((call, at) => <TrailItem key={call.id} call={call} chosen={chosenRefs(calls, at)} />)
        : folded(calls).map((part) =>
            part.kind === 'write' ? (
              <TrailItem key={part.call.id} call={part.call} chosen={chosenRefs(calls, part.at)} />
            ) : (
              <Run key={part.calls[0].id} calls={part.calls} at={part.at} trail={calls} />
            ),
          )}
    </ul>
  )
}
