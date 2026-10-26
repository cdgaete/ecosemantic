import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { withoutToken } from '@/api/client'

export type Theme = 'ecosemantic' | 'openlca'
export type EditorKind = 'system' | 'process' | 'background' | 'search' | 'results' | 'simulation'
export interface EditorTab {
  id: string
  kind: EditorKind
  title: string
  path: string
}

export interface ChosenEntry {
  systemId: string
  seq: number
  hash: string
}

export type PanelMode = 'beside' | 'expanded' | 'collapsed'

export const TRAIL_LENGTH = 4
export const PANEL_WIDTH = 420
export const NAV_WIDTH = 260

interface UiState {
  theme: Theme
  person: string | null
  panelWidth: number
  panelMode: PanelMode
  graphCovered: boolean
  navOpen: boolean
  navDocked: boolean
  paletteOpen: boolean
  navWidth: number
  pinned: EditorTab[]
  details: EditorTab | null
  lastDetails: EditorTab | null
  trail: EditorTab[]
  canvasSystemId: string | null
  chosenEntry: ChosenEntry | null
  chosenProcess: string | null
  startedImpact: string | null
  seen: Record<string, number>
  since: Record<string, number>
  collapsed: Record<string, boolean>
  formulaValues: boolean
  scaledView: boolean
  minimapOpen: boolean | null
  setTheme: (theme: Theme) => void
  setPerson: (person: string) => void
  setPanelWidth: (width: number) => void
  resetPanelWidth: () => void
  setPanelMode: (mode: PanelMode) => void
  setGraphCovered: (covered: boolean) => void
  setNavOpen: (open: boolean) => void
  setNavDocked: (docked: boolean) => void
  setPaletteOpen: (open: boolean) => void
  setNavWidth: (width: number) => void
  setCanvasSystem: (id: string | null) => void
  chooseEntry: (entry: ChosenEntry | null) => void
  chooseProcess: (id: string | null) => void
  startImpact: (systemId: string) => void
  takeStartedImpact: (systemId: string) => boolean
  look: (systemId: string, latestSeq: number) => void
  markSeen: (systemId: string, latestSeq: number) => void
  showDetails: (tab: EditorTab) => void
  showActivity: () => void
  pin: () => void
  unpin: (id: string) => void
  unpinWhere: (test: (tab: EditorTab) => boolean) => void
  toggleSection: (key: string) => void
  setFormulaValues: (shown: boolean) => void
  setScaledView: (scaled: boolean) => void
  setMinimapOpen: (open: boolean) => void
}

function stamp(theme: Theme): void {
  if (typeof document !== 'undefined') document.documentElement.setAttribute('data-theme', theme)
}

export const useUi = create<UiState>()(
  persist(
    (set, get) => ({
      theme: 'ecosemantic',
      person: null,
      panelWidth: PANEL_WIDTH,
      panelMode: 'beside',
      graphCovered: false,
      navOpen: false,
      navDocked: false,
      paletteOpen: false,
      navWidth: NAV_WIDTH,
      pinned: [],
      details: null,
      lastDetails: null,
      trail: [],
      canvasSystemId: null,
      chosenEntry: null,
      chosenProcess: null,
      startedImpact: null,
      seen: {},
      since: {},
      collapsed: {},
      formulaValues: false,
      scaledView: true,
      minimapOpen: null,
      setTheme: (theme) => {
        stamp(theme)
        set({ theme })
      },
      setPerson: (person) => set({ person }),
      setPanelWidth: (panelWidth) => set({ panelWidth }),
      resetPanelWidth: () => set({ panelWidth: PANEL_WIDTH }),
      setPanelMode: (panelMode) => set({ panelMode }),
      setGraphCovered: (graphCovered) => set({ graphCovered }),
      setNavOpen: (navOpen) => set({ navOpen }),
      setNavDocked: (navDocked) => set({ navDocked }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setNavWidth: (navWidth) => set({ navWidth }),
      setCanvasSystem: (canvasSystemId) => set((state) => (state.canvasSystemId === canvasSystemId ? {} : { canvasSystemId, chosenEntry: null, chosenProcess: null })),
      chooseEntry: (chosenEntry) => set({ chosenEntry }),
      chooseProcess: (chosenProcess) => set({ chosenProcess }),
      startImpact: (startedImpact) => set({ startedImpact }),
      takeStartedImpact: (systemId) => {
        if (get().startedImpact !== systemId) return false
        set({ startedImpact: null })
        return true
      },
      look: (systemId, latestSeq) =>
        set((state) => ({
          since: systemId in state.since ? state.since : { ...state.since, [systemId]: state.seen[systemId] ?? latestSeq },
          seen: { ...state.seen, [systemId]: Math.max(state.seen[systemId] ?? 0, latestSeq) },
        })),
      markSeen: (systemId, latestSeq) => set((state) => ({ since: { ...state.since, [systemId]: latestSeq }, seen: { ...state.seen, [systemId]: Math.max(state.seen[systemId] ?? 0, latestSeq) } })),
      showDetails: (shown) =>
        set((state) => {
          const tab = { ...shown, path: withoutToken(shown.path) }
          const at = state.trail.findIndex((t) => t.id === tab.id)
          const trail = at >= 0 ? [...state.trail.slice(0, at), tab] : [...state.trail, tab].slice(-TRAIL_LENGTH)
          const panelMode = state.panelMode === 'collapsed' ? 'beside' : state.panelMode
          return { details: tab, lastDetails: tab, trail, graphCovered: true, panelMode, pinned: state.pinned.map((p) => (p.id === tab.id ? tab : p)) }
        }),
      showActivity: () => set({ details: null, trail: [] }),
      pin: () =>
        set((state) => {
          const held = state.details
          if (held === null || state.pinned.some((p) => p.id === held.id)) return {}
          return { pinned: [...state.pinned, held] }
        }),
      unpin: (id) => set((state) => ({ pinned: state.pinned.filter((p) => p.id !== id) })),
      unpinWhere: (test) => set((state) => ({ pinned: state.pinned.filter((p) => !test(p)) })),
      toggleSection: (key) => set((state) => ({ collapsed: { ...state.collapsed, [key]: !state.collapsed[key] } })),
      setFormulaValues: (shown) => set({ formulaValues: shown }),
      setScaledView: (scaledView) => set({ scaledView }),
      setMinimapOpen: (open) => set({ minimapOpen: open }),
    }),
    {
      name: 'ecosemantic-page',
      merge: (persisted, current) => ({ ...current, ...(persisted as Partial<UiState>), scaledView: current.scaledView }),
      partialize: (state) => ({
        theme: state.theme,
        person: state.person,
        panelWidth: state.panelWidth,
        panelMode: state.panelMode,
        navDocked: state.navDocked,
        navWidth: state.navWidth,
        pinned: state.pinned,
        seen: state.seen,
        collapsed: state.collapsed,
        formulaValues: state.formulaValues,
        minimapOpen: state.minimapOpen,
      }),
      onRehydrateStorage: () => (state) => stamp(state?.theme ?? 'ecosemantic'),
    },
  ),
)

stamp(useUi.getState().theme)
