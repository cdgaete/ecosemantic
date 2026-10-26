import { useSystem, useValidation } from '@/api/queries'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'

export function ValidationBadge({ id }: { id: string }) {
  const validation = useValidation(id)
  const to = paths.systemPage(id, 'statistics')
  if (validation.error)
    return (
      <AppLink to={to} title={validation.error.message} className="text-warning hover:underline">
        ⚠ Not validated
      </AppLink>
    )
  if (!validation.data) return null
  const issues = validation.data.value.errors.length
  return (
    <AppLink to={to} className={issues === 0 ? 'text-success hover:underline' : 'text-warning hover:underline'}>
      {issues === 0 ? '✓ Valid' : `⚠ ${issues} issue${issues === 1 ? '' : 's'}`}
    </AppLink>
  )
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
