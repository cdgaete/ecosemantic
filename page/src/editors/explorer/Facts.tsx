export function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid grid-cols-1 gap-1 pt-1 text-xs">
      {rows.map(([label, value]) => (
        <div key={label} className="flex min-w-0 gap-2">
          <dt className="w-28 shrink-0 text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
