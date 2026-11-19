import { shortId } from '@/lib/format'
import { cn } from '@/lib/utils'
import { MACHINE } from '@/window/DataTable'

const TRAILING_ID = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/

export function Message({ text }: { text: string }) {
  const trailing = TRAILING_ID.exec(text)
  if (trailing === null) return <>{text}</>
  const id = trailing[1]
  return (
    <>
      {text.slice(0, trailing.index)}
      <span className={cn('text-muted-foreground', MACHINE)} title={id}>
        {shortId(id)}
      </span>
    </>
  )
}
