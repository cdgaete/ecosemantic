import { useRerun } from '@/api/queries'
import type { Call, Json } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { movedSince } from '@/lib/hashes'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { cn } from '@/lib/utils'
import { refKey } from './chosen'

function speaking(value: Json): string | null {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return String(value.length)
  if (value !== null && typeof value === 'object') return String(Object.keys(value).length)
  return null
}

function argumentsShown(arguments_: Call['arguments']): [string, string][] {
  return Object.entries(arguments_).flatMap(([key, value]) => {
    const said = key === 'product_system_id' ? null : speaking(value)
    return said === null ? [] : [[key, said] as [string, string]]
  })
}

export function TrailItem({ call, chosen }: { call: Call; chosen: Set<string> }) {
  const rerun = useRerun()
  const summary = call.summary
  const args = argumentsShown(call.arguments)
  const again = rerun.data?.value
  return (
    <li className="py-0.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className={cn('font-medium', call.outcome === 'error' && 'text-destructive')}>{call.tool}</span>
        {args.map(([key, value]) => (
          <span key={key} className="max-w-64 truncate text-muted-foreground" title={value}>
            {key}: {value}
          </span>
        ))}
        {summary && summary.count !== null ? (
          <span>
            {summary.count}
            {summary.more ? '+' : ''} {summary.noun}
          </span>
        ) : null}
        {call.effect === 'read' || call.effect === 'compute' ? (
          <button type="button" className="ml-auto text-accent hover:underline" disabled={rerun.isPending} onClick={() => rerun.mutate(call.id)}>
            Run again
          </button>
        ) : null}
      </div>
      {summary && summary.items.length > 0 ? (
        <ul className="pl-3">
          {summary.items.map((item, at) => {
            const key = refKey(item.database, item.ref)
            return (
              <li key={at} className="flex items-baseline gap-1.5">
                {key !== null && chosen.has(key) ? (
                  <span aria-label="chosen" className="text-success">
                    ✔
                  </span>
                ) : null}
                {item.kind === 'background' && item.database !== null && item.ref !== null ? (
                  <AppLink to={paths.background(item.database, item.ref)} className="truncate hover:underline">
                    {item.label}
                  </AppLink>
                ) : (
                  <span className="truncate">{item.label}</span>
                )}
                {item.detail ? <span className="text-muted-foreground">{item.detail}</span> : null}
              </li>
            )
          })}
        </ul>
      ) : null}
      {summary?.scores.map((score) => (
        <p key={score.method} className="pl-3">
          {score.method}: {formatAmount(score.value)} {score.unit}
        </p>
      ))}
      {call.error ? <p className="pl-3 text-destructive">{call.error.message}</p> : null}
      {rerun.error ? <p className="pl-3 text-destructive">{rerun.error.message}</p> : null}
      {again ? (
        <div className="pl-3">
          {movedSince(again.at_hash, again.hash_now) ? <p className="text-warning">As of now: the system changed since this call.</p> : null}
          <pre className="max-h-48 overflow-auto rounded-sm bg-muted p-1 text-xs">{JSON.stringify(again.result, null, 2)}</pre>
        </div>
      ) : null}
    </li>
  )
}
