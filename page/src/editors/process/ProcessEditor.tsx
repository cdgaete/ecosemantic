import { useEffect } from 'react'
import { Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useSystem } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import { paths, useGo } from '@/lib/paths'
import { PageTabs } from '@/window/PageTabs'
import { useUi } from '@/store/ui'
import { runCanvas } from '@/window/shortcuts'
import { useEditorTab } from '@/window/useEditorTab'
import { InputsOutputsPage } from './InputsOutputsPage'
import { ProcessGeneralPage } from './ProcessGeneralPage'

export function ProcessEditor() {
  const { id = '', code = '' } = useParams()
  const location = useLocation()
  const read = useSystem(id)
  const go = useGo()
  useSystemStream(id, go)
  const process = read.data?.value.processes.find((p) => p.code === code)
  useEditorTab({ id: `process:${id}:${code}`, kind: 'process', title: process?.name ?? code, path: location.pathname })
  const onCanvas = useUi((s) => s.canvasSystemId === id)
  const chooseProcess = useUi((s) => s.chooseProcess)
  const processId = process?.id
  useEffect(() => {
    if (processId === undefined || !onCanvas) return
    chooseProcess(processId)
    runCanvas({ show: code })
  }, [processId, code, onCanvas, chooseProcess])
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  if (!process) return <p className="p-4 text-destructive">No process {code} in {read.data.value.name}.</p>
  const active = location.pathname.endsWith('/io') ? 'io' : 'general'
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto pb-3">
        <Routes>
          <Route index element={<ProcessGeneralPage systemId={id} process={process} />} />
          <Route path="general" element={<ProcessGeneralPage systemId={id} process={process} />} />
          <Route path="io" element={<InputsOutputsPage systemId={id} system={read.data.value} process={process} />} />
        </Routes>
      </div>
      <PageTabs
        pages={[
          { key: 'general', label: 'General information', path: paths.process(id, code, 'general') },
          { key: 'io', label: 'Inputs/Outputs', path: paths.process(id, code, 'io') },
        ]}
        active={active}
      />
    </div>
  )
}
