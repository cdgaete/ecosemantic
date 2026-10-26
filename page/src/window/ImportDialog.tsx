import { useState } from 'react'
import { ApiError } from '@/api/client'
import { useReturnPackage, useReturnTables } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { useUi } from '@/store/ui'
import type { Format } from './menus'

const TITLE: Record<Format, string> = { tables: 'Import tables', openlca: 'Import an openLCA package' }
const CARRIES: Record<Format, string> = {
  tables: 'The folder Export ▸ Tables wrote, edited and zipped. It stores the parameter space; a folder whose model.yaml was edited is refused.',
  openlca:
    'The zip openLCA exported from the package Export ▸ openLCA package wrote. A package exported before a later write is refused; to return it over those writes, give the number of the system\'s last entry.',
}

type Refusal = Record<string, string | number | null>

export function ImportDialog({ systemId, format, onClose }: { systemId: string; format: Format; onClose: () => void }) {
  const person = useUi((s) => s.person)
  const setPerson = useUi((s) => s.setPerson)
  const [actor, setActor] = useState(person ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [atEntry, setAtEntry] = useState('')
  const tables = useReturnTables(systemId)
  const openlca = useReturnPackage(systemId)
  const sent = format === 'tables' ? tables : openlca
  const refusals = sent.error instanceof ApiError && Array.isArray(sent.error.details.refusals) ? (sent.error.details.refusals as Refusal[]) : []
  const columns = refusals.length > 0 ? Object.keys(refusals[0]) : []
  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent>
        <DialogTitle>{TITLE[format]}</DialogTitle>
        <p className="text-xs text-muted-foreground">{CARRIES[format]}</p>
        {person ? null : (
          <label className="flex flex-col gap-1 text-xs">
            Your name
            <input className="rounded-sm border bg-background px-1.5 py-1" value={actor} onChange={(e) => setActor(e.target.value)} />
          </label>
        )}
        <label className="flex flex-col gap-1 text-xs">
          File
          <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {format === 'openlca' ? (
          <label className="flex flex-col gap-1 text-xs">
            Exported at entry (optional)
            <input className="rounded-sm border bg-background px-1.5 py-1" inputMode="numeric" value={atEntry} onChange={(e) => setAtEntry(e.target.value.trim())} />
          </label>
        ) : null}
        {sent.error ? <p className="text-xs text-destructive">{sent.error.message}</p> : null}
        {refusals.length > 0 ? (
          <table className="w-full text-[11.5px]">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} className="border-b px-1 py-0.5 text-left font-semibold">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {refusals.map((refusal, at) => (
                <tr key={at}>
                  {columns.map((column) => (
                    <td key={column} className="border-b px-1 py-0.5">
                      {String(refusal[column] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {sent.data ? <p className="text-xs text-success">Imported as entry #{sent.data.seq}</p> : null}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button
            size="sm"
            disabled={file === null || actor === '' || sent.isPending}
            onClick={() => {
              if (file === null) return
              if (!person) setPerson(actor)
              if (format === 'openlca') openlca.mutate({ file, actor, atEntry })
              else tables.mutate({ file, actor })
            }}
          >
            Import
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
