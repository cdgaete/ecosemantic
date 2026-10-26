export function Hint({ of }: { of: { hint: string | null; has_more?: boolean } | undefined }) {
  if (!of?.hint || of.has_more) return null
  return <p className="pt-1 text-xs text-muted-foreground">{of.hint}</p>
}
