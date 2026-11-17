import { Switch } from '@/components/ui/switch'

export function ListingFilter({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 py-1">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <input
        id={id}
        className="min-w-0 flex-1 rounded-sm border bg-background px-1.5 py-0.5 text-xs"
        placeholder="Filter…"
        value={value}
        onChange={(event) => onChange(event.target.value)}
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
  options: string[]
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
          <option key={option} value={option}>
            {option}
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

export function MorePages({ shown, onMore }: { shown: boolean; onMore: () => void }) {
  if (!shown) return null
  return (
    <button type="button" className="mt-1 self-start text-xs text-accent" onClick={onMore}>
      More…
    </button>
  )
}

export function ShowTree({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="pb-1 text-xs text-accent @3xl:hidden" onClick={onClick}>
      Show the tree
    </button>
  )
}
