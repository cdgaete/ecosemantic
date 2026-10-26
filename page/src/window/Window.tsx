import { Allotment, setSashSize, type AllotmentHandle } from 'allotment'
import 'allotment/dist/style.css'
import { useEffect, useRef } from 'react'
import { useLocation, useMatch } from 'react-router-dom'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { useProcessStream } from '@/api/processStream'
import { useUi } from '@/store/ui'
import { Breadcrumb } from './Breadcrumb'
import { Canvas } from './Canvas'
import { MenuBar } from './MenuBar'
import { NavPane } from './NavPane'
import { DOCKS_FROM } from './navigation'
import { Panel } from './Panel'
import { PanelRail } from './PanelRail'
import { PinnedStrip } from './PinnedStrip'
import { TopBar } from './TopBar'
import { useShortcuts } from './shortcuts'
import { useMinWidth } from './useMinWidth'

setSashSize(10)

export function Window() {
  useProcessStream()
  useShortcuts()
  const split = useRef<AllotmentHandle>(null)
  const location = useLocation()
  const named = useMatch('/systems/:id/*')?.params.id ?? null
  const systemId = useUi((s) => s.canvasSystemId)
  const setCanvasSystem = useUi((s) => s.setCanvasSystem)
  const panelWidth = useUi((s) => s.panelWidth)
  const setPanelWidth = useUi((s) => s.setPanelWidth)
  const resetPanelWidth = useUi((s) => s.resetPanelWidth)
  const panelMode = useUi((s) => s.panelMode)
  const setPanelMode = useUi((s) => s.setPanelMode)
  const graphCovered = useUi((s) => s.graphCovered)
  const navOpen = useUi((s) => s.navOpen)
  const setNavOpen = useUi((s) => s.setNavOpen)
  const navDocked = useUi((s) => s.navDocked)
  const setNavDocked = useUi((s) => s.setNavDocked)
  const navWidth = useUi((s) => s.navWidth)
  const setNavWidth = useUi((s) => s.setNavWidth)
  const beside = useMinWidth(768)
  const docks = useMinWidth(DOCKS_FROM)
  useEffect(() => {
    if (named !== null) setCanvasSystem(named)
    else if (location.pathname === '/') setCanvasSystem(null)
  }, [named, location.pathname, setCanvasSystem])
  const shown = useRef(location.pathname)
  useEffect(() => {
    if (shown.current === location.pathname) return
    shown.current = location.pathname
    if (useUi.getState().panelMode === 'collapsed') setPanelMode('beside')
    setNavOpen(false)
  }, [location.pathname, setPanelMode, setNavOpen])
  const main =
    systemId === null || (beside && panelMode === 'expanded') ? (
      <Panel />
    ) : beside && panelMode === 'collapsed' ? (
      <div className="flex h-full">
        <div className="min-w-0 flex-1">
          <Canvas systemId={systemId} />
        </div>
        <PanelRail systemId={systemId} />
      </div>
    ) : beside ? (
      <Allotment
        ref={split}
        onChange={(sizes) => sizes[1] && setPanelWidth(sizes[1])}
        onReset={() => {
          resetPanelWidth()
          requestAnimationFrame(() => split.current?.reset())
        }}
      >
        <Allotment.Pane minSize={320}>
          <Canvas systemId={systemId} />
        </Allotment.Pane>
        <Allotment.Pane minSize={320} preferredSize={panelWidth}>
          <Panel />
        </Allotment.Pane>
      </Allotment>
    ) : graphCovered ? (
      <Panel />
    ) : (
      <div className="flex h-full flex-col">
        <div className="min-h-0 flex-1">
          <Canvas systemId={systemId} />
        </div>
        <button type="button" className="border-t bg-chrome py-1 text-xs" onClick={() => useUi.getState().setGraphCovered(true)}>
          Show panel
        </button>
      </div>
    )
  return (
    <div className="flex h-screen flex-col">
      <TopBar menu={<MenuBar />} />
      <PinnedStrip />
      <div className="min-h-0 flex-1">
        {docks ? (
          <Allotment
            onChange={(sizes) => navDocked && sizes[0] && setNavWidth(sizes[0])}
            onVisibleChange={(index, visible) => index === 0 && setNavDocked(visible)}
          >
            <Allotment.Pane minSize={200} preferredSize={navWidth} snap visible={navDocked}>
              {navDocked ? <NavPane /> : null}
            </Allotment.Pane>
            <Allotment.Pane minSize={320}>{main}</Allotment.Pane>
          </Allotment>
        ) : (
          main
        )}
      </div>
      <Breadcrumb />
      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <NavPane />
        </SheetContent>
      </Sheet>
    </div>
  )
}
