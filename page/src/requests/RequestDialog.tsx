import { useSystem } from '@/api/queries'
import type { Entity } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RequestForm } from './RequestForm'
import { useRequestDialog } from './useRequestDialog'

export function RequestDialog() {
  const target = useRequestDialog((s) => s.target)
  const close = useRequestDialog((s) => s.close)
  return (
    <Dialog open={target !== null} onOpenChange={(open) => (open ? null : close())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New request</DialogTitle>
        </DialogHeader>
        {target ? <Body target={target} onDone={close} /> : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="ghost" size="sm">
              Cancel
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Body({ target, onDone }: { target: { systemId: string; entity?: Entity; entityId?: string }; onDone: () => void }) {
  const read = useSystem(target.systemId)
  if (read.error) return <p className="text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="text-muted-foreground">Loading…</p>
  const hash = read.data.value.hash
  if (hash === null) return <p className="text-warning">The stored product system carries no hash yet.</p>
  return <RequestForm systemId={target.systemId} atHash={hash} entity={target.entity} entityId={target.entityId} onDone={onDone} />
}
