import { useEffect, useLayoutEffect, useState } from 'react'
import { Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useSystem, useSystemAs } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import { paths, useGo } from '@/lib/paths'
import { EditorHeader } from '@/window/EditorHeader'
import { PageTabs } from '@/window/PageTabs'
import { useUi } from '@/store/ui'
import { runCanvas } from '@/window/shortcuts'
import { StateRefused } from '@/window/StateLine'
import { useFollowedExchange } from '@/window/supplier'
import { SupplierReturn } from '@/window/SupplierReturn'
import { useCanvasVariant } from '@/window/useCanvasState'
import { useEditorTab } from '@/window/useEditorTab'
import { useMinWidth } from '@/window/useMinWidth'
import { InputsOutputsPage } from './InputsOutputsPage'
import { ProcessGeneralPage } from './ProcessGeneralPage'

export function ProcessEditor() {
  const { id = '', code = '' } = useParams()
  const location = useLocation()
  const read = useSystem(id)
  const go = useGo()
  useSystemStream(id, go)
  const state = useCanvasVariant(read.data?.value)
  const under = useSystemAs(id, state?.name ?? null)
  const system = state === null ? read.data?.value : under.data?.value
  const process = system?.processes.find((p) => p.code === code)
  useEditorTab({ id: `process:${id}:${code}`, kind: 'process', title: process?.name ?? code, path: location.pathname })
  const onCanvas = useUi((s) => s.canvasSystemId === id)
  const narrow = !useMinWidth(768)
  const chooseProcess = useUi((s) => s.chooseProcess)
  const processId = process?.id
  const followed = useFollowedExchange()
  const [body, setBody] = useState<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    if (followed === null || body === null) return
    body.scrollTop = followed.scroll
  }, [followed, body])
  useEffect(() => {
    if (processId === undefined || !onCanvas) return
    chooseProcess(processId)
    if (!narrow) runCanvas({ show: code })
  }, [processId, code, onCanvas, narrow, chooseProcess])
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  if (state !== null && under.error) return <StateRefused state={state} message={under.error.message} />
  if (system === undefined) return <p className="p-4 text-muted-foreground">Loading…</p>
  if (!process) return <p className="p-4 text-destructive">No process {code} in {system.name}.</p>
  const active = location.pathname.endsWith('/io') ? 'io' : 'general'
  return (
    <div className="flex h-full flex-col">
      <EditorHeader icon="process" page={active === 'io' ? 'Inputs/Outputs' : 'General information'} entity={process.name} state={state} />
      <PageTabs
        at="top"
        pages={[
          { key: 'general', label: 'General information', path: paths.process(id, code, 'general') },
          { key: 'io', label: 'Inputs/Outputs', path: paths.process(id, code, 'io') },
        ]}
        active={active}
      />
      <div ref={setBody} data-scroll-body className="min-h-0 flex-1 overflow-auto pb-3">
        <SupplierReturn className="px-4 pt-2" />
        <Routes>
          <Route index element={<ProcessGeneralPage systemId={id} process={process} />} />
          <Route path="general" element={<ProcessGeneralPage systemId={id} process={process} />} />
          <Route path="io" element={<InputsOutputsPage systemId={id} system={system} process={process} state={state} />} />
        </Routes>
      </div>
    </div>
  )
}
