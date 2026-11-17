import { useEffect, useRef } from 'react'
import { Outlet, useLocation, useMatch } from 'react-router-dom'
import { BuildLine } from '@/activity/BuildLine'
import { Timeline } from '@/activity/Timeline'
import { useProcessStream } from '@/api/processStream'
import { cn } from '@/lib/utils'
import { useUi } from '@/store/ui'
import { Canvas } from './Canvas'
import { useIslandClearance } from './clearance'
import { Dock } from './Dock'
import { openInspector, opensInspector, useInspectorShown } from './inspector'
import { Inspector } from './Inspector'
import { MenuButton, MenuStrip } from './MenuBar'
import { NameIsland } from './NameIsland'
import { closeNavigation } from './navigation'
import { NavigationSheet } from './NavigationSheet'
import { Palette } from './Palette'
import { useShortcuts } from './shortcuts'
import { Slot, SlotsProvider } from './slots'
import { useCanvasState } from './useCanvasState'
import { useMenus } from './useMenus'
import { useMinWidth } from './useMinWidth'

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
  useIslandClearance(
    grid,
    `${named ?? 'no system'} ${inspectorShown ? 'shown' : 'hidden'} ${inspectorMode} ${narrow ? 'narrow' : 'roomy'} ${toolsOpen ? 'tools open' : 'tools closed'}`,
  )
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
    if (opensInspector(location.pathname)) openInspector()
    closeNavigation()
  }, [location.pathname])
  return (
    <SlotsProvider>
      <div className="relative h-screen overflow-hidden">
        {named === null ? null : (
          <div className="absolute inset-0">
            <Canvas systemId={named} />
          </div>
        )}
        <div
          ref={grid}
          className={cn(
            'pointer-events-none absolute inset-0 grid gap-3 p-3 [&>*]:pointer-events-auto [&>*]:min-w-0',
            narrow ? 'grid-cols-[auto_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[auto_minmax(0,1fr)_auto] grid-rows-[auto_minmax(0,1fr)_auto]',
          )}
        >
          <Dock menus={wide ? null : <MenuButton menus={menus} go={go} />} view={narrow || named === null ? null : <Slot name="view" />} />
          <NameIsland menus={wide ? <MenuStrip menus={menus} go={go} /> : null} systemId={named} />
          {named === null ? (
            <section
              aria-label="Page"
              className={cn(
                'row-span-2 row-start-2 flex min-h-0 flex-col overflow-hidden rounded-xl border bg-background',
                narrow ? 'col-span-2 col-start-1' : 'col-span-2 col-start-2',
              )}
            >
              <div className="@container min-h-0 flex-1 overflow-auto">
                <Outlet />
              </div>
            </section>
          ) : (
            <>
              {narrow ? null : (
                <div data-clear="top" className="col-start-3 row-start-1 min-w-0 justify-self-end self-start">
                  <Slot name="tools" />
                </div>
              )}
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
          {narrow ? null : (
            <div data-clear="bottom" className="col-start-2 row-start-2 self-end justify-self-start">
              <Slot name="minimap" />
            </div>
          )}
          <div className="col-start-2 row-start-2 self-start justify-self-center">
            <Slot name="notice" />
          </div>
          {narrow && named !== null ? <BuildLine systemId={named} live={canvas.live} toolsOpen={toolsOpen} onTools={() => setToolsOpen(!toolsOpen)} /> : null}
          <NavigationSheet />
        </div>
        {dialog}
        <Palette menus={menus} go={go} />
      </div>
    </SlotsProvider>
  )
}
