import { useSystem, useValidation } from '@/api/queries'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'

export function ValidationMark({ id, issues, error }: { id: string; issues: number | null; error: string | null }) {
  const to = paths.systemPage(id, 'statistics')
  if (error)
    return (
      <AppLink to={to} title={error} className="text-warning hover:underline">
        ⚠ Not validated
      </AppLink>
    )
  if (issues === null) return null
  return (
    <AppLink to={to} className={issues === 0 ? 'text-success hover:underline' : 'text-warning hover:underline'}>
      {issues === 0 ? '✓ Valid' : `⚠ ${issues} issue${issues === 1 ? '' : 's'}`}
    </AppLink>
  )
}

export function ValidationBadge({ id }: { id: string }) {
  const validation = useValidation(id)
  const issues = validation.data ? validation.data.value.errors.length : null
  return <ValidationMark id={id} issues={issues} error={validation.error ? validation.error.message : null} />
}

export function RequestsBadge({ id }: { id: string }) {
  const read = useSystem(id)
  const open = read.data?.open_requests ?? 0
  return (
    <AppLink to={paths.systemPage(id, 'requests')} className="hover:underline">
      ✉ {open} open request{open === 1 ? '' : 's'}
    </AppLink>
  )
}

export function CanvasBadge() {
  return <span className="shrink-0 rounded-full bg-selected px-1.5 text-xs font-normal text-muted-foreground">on the canvas</span>
}
