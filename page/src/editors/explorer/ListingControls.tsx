import { Switch } from '@/components/ui/switch'
import { formatAmount } from '@/lib/format'
import { usePausedDraft } from './usePausedDraft'

export function ListingFilter({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  const { draft, type } = usePausedDraft(value, onChange)
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 py-1">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <input
        id={id}
        className="min-w-0 flex-1 rounded-sm border bg-background px-1.5 py-0.5 text-xs"
        placeholder="Filter…"
        value={draft}
        onChange={(event) => type(event.target.value)}
      />
    </div>
  )
}

export function ListingSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  return (
    <label className="flex min-w-0 max-w-full items-center gap-1 text-xs">
      {label}
      <select
        id={id}
        className="min-w-0 max-w-full rounded-sm border bg-background px-1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">any</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function WholeDatabaseSwitch({ id, checked, onChange }: { id: string; checked: boolean; onChange: (on: boolean) => void }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 pb-1 text-xs">
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
      <label htmlFor={id}>Search the whole database</label>
    </div>
  )
}

export function Pager({ previous, next, onPage }: { previous: string | null; next: string | null; onPage: (cursor: string) => void }) {
  if (previous === null && next === null) return null
  return (
    <div className="mt-1 flex min-w-0 items-center gap-3 text-xs">
      {previous === null ? null : (
        <button type="button" className="text-accent" onClick={() => onPage(previous)}>
          Previous page
        </button>
      )}
      {next === null ? null : (
        <button type="button" className="text-accent" onClick={() => onPage(next)}>
          Next page
        </button>
      )}
    </div>
  )
}

export function Count({ kept, of }: { kept: number | null; of: number }) {
  return (
    <span className="text-xs tabular-nums text-muted-foreground">
      {kept === null ? formatAmount(of) : `${formatAmount(kept)} of ${formatAmount(of)}`}
    </span>
  )
}

export function ShowTree({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="pb-1 text-xs text-accent @3xl:hidden" onClick={onClick}>
      Show the tree
    </button>
  )
}
