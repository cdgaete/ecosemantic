import type { ReactNode } from 'react'
import { Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useLog, useSystem, useSystemAs, useVersion } from '@/api/queries'
import { useSystemStream } from '@/api/stream'
import type { ProductSystem } from '@/api/types'
import { paths, isActivityPath, useGo } from '@/lib/paths'
import { shortHash } from '@/lib/format'
import { PageTabs } from '@/window/PageTabs'
import { StateRefused } from '@/window/StateLine'
import { useCanvasVariant, type CanvasVariant } from '@/window/useCanvasState'
import { useEditorTab } from '@/window/useEditorTab'
import { entryAtHash } from './entries'
import { GeneralInformationPage } from './GeneralInformationPage'
import { LogPage } from './LogPage'
import { ParametersPage } from './ParametersPage'
import { RequestsPage } from './RequestsPage'
import { SimulationsPage } from './SimulationsPage'
import { StatisticsPage } from './StatisticsPage'
import { systemPages, SYSTEM_PAGES } from './pages'

export interface SystemView {
  id: string
  system: ProductSystem
  openRequests: number
  version: string | null
  state: CanvasVariant | null
}

interface StateRead {
  system: ProductSystem | undefined
  error: Error | null
}

export function SystemEditor() {
  const { id = '' } = useParams()
  const location = useLocation()
  const read = useSystem(id)
  const go = useGo()
  useSystemStream(id, go)
  const state = useCanvasVariant(read.data?.value)
  const under = useSystemAs(id, state?.name ?? null)
  const activity = isActivityPath(location.pathname, id)
  useEditorTab(activity ? null : { id: `system:${id}`, kind: 'system', title: read.data?.value.name ?? 'Product system', path: location.pathname })
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  const view: SystemView = { id, system: read.data.value, openRequests: read.data.open_requests, version: null, state }
  return <Pages view={view} under={{ system: under.data?.value, error: under.error }} />
}

export function VersionEditor() {
  const { id = '', hash = '' } = useParams()
  const location = useLocation()
  const read = useVersion(id, hash)
  useEditorTab({ id: `version:${id}:${hash}`, kind: 'system', title: `${read.data?.name ?? 'Product system'} @ ${shortHash(hash)}`, path: location.pathname })
  if (read.error) return <p className="p-4 text-destructive">{read.error.message}</p>
  if (!read.data) return <p className="p-4 text-muted-foreground">Loading…</p>
  const view: SystemView = { id, system: read.data, openRequests: 0, version: hash, state: null }
  return (
    <>
      <VersionBanner id={id} hash={hash} />
      <Pages view={view} under={{ system: read.data, error: null }} />
    </>
  )
}

function VersionBanner({ id, hash }: { id: string; hash: string }) {
  const log = useLog(id)
  const named = `Read-only: the product system as it was at ${shortHash(hash)}`
  if (log.error) return <div className="border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">{`${named}. ${log.error.message}`}</div>
  if (!log.data) return <div className="border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">{`${named}. Loading the log…`}</div>
  const entry = entryAtHash(log.data.value, hash)
  return (
    <div className="border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">
      {entry ? `${named}, entry #${entry.seq} — ${entry.message}.` : `${named}. No log entry names this hash.`}
    </div>
  )
}

function Pages({ view, under }: { view: SystemView; under: StateRead }) {
  const location = useLocation()
  const live = view.version === null
  const activity = live && isActivityPath(location.pathname, view.id)
  const stored: SystemView = { ...view, state: null }
  const stated = view.state === null ? view.system : under.system
  const statePage = (draw: (page: SystemView) => ReactNode): ReactNode => {
    const { state } = view
    if (state === null) return draw(view)
    if (stated === undefined) {
      return under.error === null ? <p className="p-4 text-muted-foreground">Loading…</p> : <StateRefused state={state} message={under.error.message} />
    }
    return draw({ ...view, system: stated })
  }
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto pb-3">
        <Routes>
          <Route index element={live ? <LogPage view={stored} /> : statePage((page) => <GeneralInformationPage view={page} />)} />
          <Route path="log" element={<LogPage view={stored} />} />
          <Route path="graph" element={<LogPage view={stored} />} />
          <Route path="general" element={statePage((page) => <GeneralInformationPage view={page} />)} />
          <Route path="parameters" element={statePage((page) => <ParametersPage view={page} />)} />
          <Route path="statistics" element={statePage((page) => <StatisticsPage view={page} />)} />
          {live ? <Route path="requests" element={<RequestsPage view={stored} />} /> : null}
          {live ? <Route path="simulations" element={<SimulationsPage view={stored} />} /> : null}
        </Routes>
      </div>
      {activity ? null : <SystemPageTabs view={view} />}
    </div>
  )
}

export function SystemPageTabs({ view }: { view: SystemView }) {
  const location = useLocation()
  const base = view.version === null ? paths.system(view.id) : paths.version(view.id, view.version)
  const segment = location.pathname.startsWith(`${base}/`) ? location.pathname.slice(base.length + 1).split('/')[0] : ''
  const active = SYSTEM_PAGES.includes(segment) ? segment : 'general'
  return <PageTabs pages={systemPages(view.id, view.version)} active={active} />
}
