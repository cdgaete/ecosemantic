import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Outlet, useLocation, useMatch } from 'react-router-dom'
import { BuildLine } from '@/activity/BuildLine'
import { Timeline } from '@/activity/Timeline'
import { withoutToken } from '@/api/client'
import { useProcessStream } from '@/api/processStream'
import { ResultBand } from '@/editors/results/ResultBand'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { Canvas } from './Canvas'
import { useIslandClearance } from './clearance'
import { Dock } from './Dock'
import { IconButton } from './IconButton'
import { openInspector, opensInspector, useInspectorShown } from './inspector'
import { Inspector } from './Inspector'
import { MenuButton, MenuStrip } from './MenuBar'
import { NameIsland } from './NameIsland'
import { closeNavigation } from './navigation'
import { NavigationSheet } from './NavigationSheet'
import { Palette } from './Palette'
import { dockedOf, originAfter, sheetOf, systemOf, useSheet, type Place } from './sheets'
import { useToolsPlace } from './tools'
import { ToolsIsland } from './ToolsIsland'
import { LEAVE_EVENT, useShortcuts } from './shortcuts'
import { Slot, SlotsProvider } from './slots'
import { useCanvasState } from './useCanvasState'
import { useMenus } from './useMenus'
import { useMinWidth } from './useMinWidth'

const CLOSE = { explorer: 'Close the explorer', results: 'Close the results' }

export function Window() {
  useProcessStream()
  useShortcuts()
  const location = useLocation()
  const named = useMatch('/systems/:id/*')?.params.id ?? null
  const versioned = useMatch('/systems/:id/versions/:hash/*') !== null
  const setCanvasSystem = useUi((s) => s.setCanvasSystem)
  const chooseEntry = useUi((s) => s.chooseEntry)
  const canvas = useCanvasState(named)
  const { menus, dialog, go } = useMenus()
  const wide = useMinWidth(1024)
  const narrow = !useMinWidth(768)
  const toolsOpen = useUi((s) => s.toolsOpen)
  const setToolsOpen = useUi((s) => s.setToolsOpen)
  const grid = useRef<HTMLDivElement>(null)
  const inspectorShown = useInspectorShown()
  const inspectorMode = useUi((s) => s.inspector)
  const setOrigin = useUi((s) => s.setOrigin)
  const sheet = useSheet()
  const sheetTo = sheet?.to ?? null
  const docked = sheet?.docked === true && named !== null
  const overlay = sheet !== null && !docked
  const behind = named === null && sheetTo !== null && !narrow ? systemOf(sheetTo) : null
  const drawn = named ?? behind
  const paged = named === null || overlay
  const setSheetOpen = useUi((s) => s.setSheetOpen)
  const toolsMoved = useToolsPlace((s) => (s.live ?? s.held) !== null)
  useIslandClearance(
    grid,
    `${named ?? 'no system'} ${inspectorShown ? 'shown' : 'hidden'} ${inspectorMode} ${narrow ? 'narrow' : 'roomy'} ${toolsOpen ? 'tools open' : 'tools closed'} ${toolsMoved ? 'tools moved' : 'tools docked'} ${docked ? 'result docked' : 'result closed'}`,
    overlay && drawn !== null,
  )
  const last = useRef<Place | null>(null)
  useEffect(() => {
    const here: Place = { address: withoutToken(`${location.pathname}${location.search}`), kind: sheetOf(location.pathname) }
    const origin = originAfter(last.current, here, useUi.getState().origins)
    last.current = here
    if (here.kind !== null && origin !== undefined) setOrigin(here.kind, origin)
  }, [location.pathname, location.search, setOrigin])
  useEffect(() => {
    if (sheetTo === null) return
    const leave = () => go(sheetTo)
    window.addEventListener(LEAVE_EVENT, leave)
    return () => window.removeEventListener(LEAVE_EVENT, leave)
  }, [sheetTo, go])
  useEffect(() => {
    if (docked && narrow) setSheetOpen(false)
  }, [docked, narrow, setSheetOpen])
  useEffect(() => {
    if (named !== null) setCanvasSystem(named)
    else if (location.pathname === '/') setCanvasSystem(null)
  }, [named, location.pathname, setCanvasSystem])
  const shownPath = useRef(location.pathname)
  const wasVersioned = useRef(versioned)
  useEffect(() => {
    if (wasVersioned.current && !versioned) chooseEntry(null)
    wasVersioned.current = versioned
  }, [versioned, chooseEntry])
  useEffect(() => {
    if (shownPath.current === location.pathname) return
    shownPath.current = location.pathname
    if (opensInspector(location.pathname) && !dockedOf(location.pathname) && (narrow || sheetOf(location.pathname) === null)) openInspector()
    closeNavigation()
  }, [location.pathname, narrow])
  return (
    <SlotsProvider>
      <div className="relative h-screen overflow-hidden">
        {drawn === null ? null : (
          <div className="absolute inset-0">
            <Canvas systemId={drawn} />
          </div>
        )}
        {overlay ? <div aria-hidden data-scrim title={sheet.label} className="absolute inset-0 bg-black/30" onClick={() => go(sheet.to)} /> : null}
        <div
          ref={grid}
          className={cn(
            'pointer-events-none absolute inset-0 grid gap-3 p-3 [&>*]:pointer-events-auto [&>*]:min-w-0',
            narrow ? 'grid-cols-[auto_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[auto_minmax(0,1fr)_auto] grid-rows-[auto_minmax(0,1fr)_auto]',
            docked && !narrow && 'grid-rows-[auto_minmax(0,2fr)_minmax(0,3fr)]',
          )}
        >
          <Dock menus={wide ? null : <MenuButton menus={menus} go={go} />} view={narrow || paged ? null : <Slot name="view" />} />
          {narrow ? (
            <NameIsland menus={null} systemId={named} />
          ) : (
            <div
              className={cn(
                '!pointer-events-none col-span-2 col-start-2 row-start-1 grid min-w-0 items-start gap-3 [&>*]:pointer-events-auto [&>*]:min-w-0',
                paged ? 'grid-cols-[minmax(0,1fr)_auto]' : 'grid-cols-[minmax(260px,1fr)_auto_minmax(0,1fr)]',
              )}
            >
              <NameIsland menus={wide ? <MenuStrip menus={menus} go={go} /> : null} systemId={named} />
              {paged ? null : <ToolsIsland />}
              {sheet === null ? null : (
                <div className="col-start-2 row-start-1 justify-self-end rounded-xl border bg-chrome/95 p-1 shadow-lg">
                  <IconButton label={CLOSE[sheet.kind]} shortcut="dismiss" side="left" onClick={() => go(sheet.to)}>
                    <X />
                  </IconButton>
                </div>
              )}
            </div>
          )}
          {paged ? (
            <section
              aria-label="Page"
              className={cn(
                'row-span-2 row-start-2 flex min-h-0 flex-col overflow-hidden rounded-xl border bg-background',
                narrow ? 'col-span-2 col-start-1' : 'col-span-2 col-start-2',
                sheet !== null && wide && 'mr-10 mb-6 shadow-lg',
              )}
            >
              <div className="@container min-h-0 flex-1 overflow-auto">
                <Outlet />
              </div>
            </section>
          ) : docked ? (
            <section
              aria-label="Result"
              data-clear={narrow ? undefined : 'bottom'}
              className={cn(
                'flex min-h-0 flex-col overflow-hidden rounded-xl border bg-background shadow-lg',
                narrow ? 'col-span-2 col-start-1 row-span-2 row-start-2' : 'col-span-2 col-start-2 row-start-3',
              )}
            >
              {narrow ? (
                <div className="flex flex-wrap items-center gap-1 border-b p-1">
                  <ResultBand systemId={named} />
                </div>
              ) : null}
              <div className="@container min-h-0 flex-1 overflow-auto">
                <Outlet />
              </div>
            </section>
          ) : (
            <>
              {narrow && toolsOpen ? (
                <div className="col-start-2 row-start-2 flex min-w-0 max-w-full flex-col items-end justify-self-end self-end gap-1 rounded-xl border bg-chrome/95 p-1 shadow-lg">
                  <Slot name="view" />
                  <Slot name="tools" />
                </div>
              ) : null}
              <Inspector />
              {narrow ? null : <Timeline systemId={named} />}
            </>
          )}
          {narrow || paged ? null : (
            <div data-clear="bottom" className="col-start-2 row-start-2 self-end justify-self-start">
              <Slot name="minimap" />
            </div>
          )}
          {paged ? null : (
            <div className="col-start-2 row-start-2 self-start justify-self-center">
              <Slot name="notice" />
            </div>
          )}
          {narrow && named !== null && !docked ? <BuildLine systemId={named} live={canvas.live} toolsOpen={toolsOpen} onTools={() => setToolsOpen(!toolsOpen)} /> : null}
          <NavigationSheet />
        </div>
        {dialog}
        <Palette menus={menus} go={go} />
      </div>
    </SlotsProvider>
  )
}
