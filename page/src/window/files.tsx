import { useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { useSystem } from '@/api/queries'
import { demandOf, toImpactArguments } from '@/editors/results/params'
import { useResultParams } from '@/editors/results/useResultParams'
import { useUi } from '@/store/ui'
import { ImportDialog } from './ImportDialog'
import type { Format, ResultKind } from './menus'

function save(blob: Blob, name: string): void {
  const address = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = address
  link.download = name
  link.click()
  URL.revokeObjectURL(address)
}

export function useFiles(): { importFile: (format: Format) => void; downloadResult: (kind: ResultKind) => void; dialog: ReactNode } {
  const systemId = useUi((s) => s.canvasSystemId)
  const location = useLocation()
  const system = useSystem(systemId ?? '', systemId !== null)
  const resolved = useResultParams(systemId ?? '', location.search)
  const [format, setFormat] = useState<Format | null>(null)
  const downloadResult = (kind: ResultKind): void => {
    const params = resolved.params
    if (systemId === null || params === null) return
    const root = system.data?.value.reference_process ?? null
    const method = { ...(params.method_id ? { method_id: params.method_id } : {}), ...(params.impact_method ? { impact_method: params.impact_method } : {}) }
    const demand = demandOf(params, root)
    const body = kind === 'impact' ? toImpactArguments(params, root) : kind === 'contributions' ? { by: 'process', ...method, ...(demand ? { demand } : {}) } : { ...(demand ? { demand } : {}) }
    api.resultZip(systemId, kind, body).then(
      (blob) => save(blob, `${kind}.zip`),
      (error: Error) => toast.error(error.message),
    )
  }
  return {
    importFile: setFormat,
    downloadResult,
    dialog: systemId !== null && format !== null ? <ImportDialog systemId={systemId} format={format} onClose={() => setFormat(null)} /> : null,
  }
}
