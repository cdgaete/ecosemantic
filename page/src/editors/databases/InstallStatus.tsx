import { useCancelInstall } from '@/api/queries'
import type { Install } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatAgo } from '@/lib/format'

export function InstallStatus({ install }: { install: Install }) {
  const cancel = useCancelInstall()
  const since = install.started_at ?? install.posted_at
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border bg-background px-2 py-1 text-xs">
      <span className="font-medium">
        {install.draft.source} {install.draft.version ?? ''}
      </span>
      <span className="text-muted-foreground">{install.status}</span>
      {install.progress === null ? null : <span className="break-words">{install.progress.step}</span>}
      {install.progress === null || install.progress.count === null ? null : <span className="tabular-nums">{install.progress.count}</span>}
      <time dateTime={since} title={since} className="text-muted-foreground">
        {formatAgo(since)}
      </time>
      {install.open ? (
        <Button size="sm" variant="outline" onClick={() => cancel.mutate(install.id)}>
          Cancel
        </Button>
      ) : null}
    </div>
  )
}
