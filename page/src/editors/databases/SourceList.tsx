import type { DatabaseSource, SourceName } from '@/api/types'
import { cn } from '@/lib/utils'
import { Icon } from '@/window/Icon'

function requirement(source: DatabaseSource): string {
  const parts = [source.versions.length > 0 ? source.versions.join(', ') : 'a zip you hold']
  parts.push(source.credential === null ? 'no account' : `a ${source.credential} account`)
  if (source.terms) parts.push('terms to accept')
  return parts.join(' · ')
}

export function SourceList({ sources, picked = null, onPick }: { sources: DatabaseSource[]; picked?: SourceName | null; onPick: (name: SourceName) => void }) {
  return (
    <ul className="flex flex-col gap-1">
      {sources.map((source) => (
        <li key={source.name}>
          <button
            type="button"
            aria-pressed={source.name === picked}
            className={cn(
              'flex w-full min-w-0 flex-col items-start gap-0.5 rounded-md border px-2 py-1 text-left transition-colors hover:bg-foreground/8',
              source.name === picked ? 'bg-selected' : '',
            )}
            onClick={() => onPick(source.name)}
          >
            <span className="flex min-w-0 items-center gap-1.5 font-medium">
              <Icon name="database" />
              <span className="truncate">{source.name}</span>
            </span>
            <span className="text-xs break-words text-muted-foreground">{requirement(source)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
