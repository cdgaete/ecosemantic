import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'

export function CurrentValidationLine({ id }: { id: string }) {
  return (
    <p className="border-t px-4 py-2 text-muted-foreground">
      <span>Validation answers for the current document, not for this version.</span>{' '}
      <AppLink to={paths.system(id)} className="text-accent">
        Open the live product system
      </AppLink>
    </p>
  )
}
