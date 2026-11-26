import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { withoutToken } from '@/api/client'

export type Theme = 'light' | 'dark'
export type EditorKind = 'system' | 'process' | 'results' | 'simulation' | 'explorer'
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

export type InspectorMode = 'open' | 'widened' | 'closed'
export type SheetKind = 'explorer' | 'results'
export interface Offset {
  x: number
  y: number
}

interface UiState {
  theme: Theme
  person: string | null
  inspector: InspectorMode
  inspectorWidth: number | null
  resultWidth: number | null
  timelineOpen: boolean
  toolsOffset: Offset | null
  origins: Record<SheetKind, string | null>
  sheetOpen: boolean
  sheetShort: boolean
  toolsOpen: boolean
  navOpen: boolean
  paletteOpen: boolean
  pinned: EditorTab[]
  details: EditorTab | null
  lastDetails: EditorTab | null
  canvasSystemId: string | null
  canvasVariant: string | null
  chosenEntry: ChosenEntry | null
  chosenProcess: string | null
  startedImpact: string | null
  seen: Record<string, number>
  since: Record<string, number>
  collapsed: Record<string, boolean>
  navDatabases: Record<string, boolean>
  resultCategories: Record<string, string>
  explorerSchemes: Record<string, string>
  formulaValues: boolean
  scaledView: boolean
  minimapOpen: boolean | null
  setTheme: (theme: Theme) => void
  setPerson: (person: string) => void
  setInspector: (mode: InspectorMode) => void
  setInspectorWidth: (width: number | null) => void
  setResultWidth: (width: number | null) => void
  setTimelineOpen: (open: boolean) => void
  setToolsOffset: (offset: Offset | null) => void
  setOrigin: (kind: SheetKind, address: string | null) => void
  setSheetOpen: (open: boolean) => void
  setSheetShort: (short: boolean) => void
  setToolsOpen: (open: boolean) => void
  setNavOpen: (open: boolean) => void
  setPaletteOpen: (open: boolean) => void
  setCanvasSystem: (id: string | null) => void
  setCanvasVariant: (variant: string | null) => void
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
  toggleNavDatabase: (name: string) => void
  setFormulaValues: (shown: boolean) => void
  setScaledView: (scaled: boolean) => void
  setMinimapOpen: (open: boolean) => void
  setExplorerScheme: (database: string, scheme: string) => void
  setResultCategory: (systemId: string, methodId: string) => void
}

const THEME_OF_VERSION_1 = { cobalt: 'light', ecosemantic: 'dark', openlca: 'light' } as const satisfies Record<string, Theme>
type Version1State = Omit<Partial<UiState>, 'theme'> & { theme?: keyof typeof THEME_OF_VERSION_1 }

const INSPECTOR_OF_PANEL = { beside: 'open', expanded: 'widened', collapsed: 'closed' } as const satisfies Record<string, InspectorMode>
type Version4State = { panelMode?: keyof typeof INSPECTOR_OF_PANEL }

const RETIRED_TAB_KINDS = ['background', 'search']
const RETIRED_FIELDS = ['panelMode', 'panelWidth', 'navDocked', 'navWidth', 'graphCovered'] as const

function withoutRetiredFields(state: Partial<UiState>): Partial<UiState> {
  const kept: Record<string, unknown> = { ...state }
  for (const field of RETIRED_FIELDS) delete kept[field]
  return kept as Partial<UiState>
}

function explorerPinned(pinned: EditorTab[]): EditorTab[] {
  return pinned.map((tab) => (RETIRED_TAB_KINDS.includes(tab.kind) ? { ...tab, kind: 'explorer' } : tab))
}

function version1Theme(state: Partial<UiState>): Partial<UiState> {
  const saved = state as Version1State
  return saved.theme === undefined ? state : { ...state, theme: THEME_OF_VERSION_1[saved.theme] }
}

function migrate(persisted: unknown, version: number): UiState {
  let state = persisted as Partial<UiState> & Version4State
  if (version < 1) state = { ...state, theme: 'light' }
  else if (version < 2) state = version1Theme(state)
  if (version < 4 && Array.isArray(state.pinned)) state = { ...state, pinned: explorerPinned(state.pinned) }
  if (version < 5) {
    const { panelMode } = state
    state = { ...withoutRetiredFields(state), inspector: panelMode === undefined ? 'open' : INSPECTOR_OF_PANEL[panelMode] }
  }
  return state as UiState
}

function stamp(theme: Theme): void {
  if (typeof document !== 'undefined') document.documentElement.setAttribute('data-theme', theme)
}

export const useUi = create<UiState>()(
  persist(
    (set, get) => ({
      theme: 'light',
      person: null,
      inspector: 'open',
      inspectorWidth: null,
      resultWidth: null,
      timelineOpen: true,
      toolsOffset: null,
      origins: { explorer: null, results: null },
      sheetOpen: false,
      sheetShort: false,
      toolsOpen: false,
      navOpen: false,
      paletteOpen: false,
      pinned: [],
      details: null,
      lastDetails: null,
      canvasSystemId: null,
      canvasVariant: null,
      chosenEntry: null,
      chosenProcess: null,
      startedImpact: null,
      seen: {},
      since: {},
      collapsed: {},
      navDatabases: {},
      resultCategories: {},
      explorerSchemes: {},
      formulaValues: false,
      scaledView: true,
      minimapOpen: null,
      setTheme: (theme) => {
        stamp(theme)
        set({ theme })
      },
      setPerson: (person) => set({ person }),
      setInspector: (inspector) => set({ inspector }),
      setInspectorWidth: (inspectorWidth) => set({ inspectorWidth }),
      setResultWidth: (resultWidth) => set({ resultWidth }),
      setTimelineOpen: (timelineOpen) => set({ timelineOpen }),
      setToolsOffset: (toolsOffset) => set({ toolsOffset }),
      setOrigin: (kind, address) => set((state) => ({ origins: { ...state.origins, [kind]: address } })),
      setSheetOpen: (open) => set(open ? { sheetOpen: true, toolsOpen: false } : { sheetOpen: false }),
      setSheetShort: (sheetShort) => set({ sheetShort }),
      setToolsOpen: (open) => set(open ? { toolsOpen: true, sheetOpen: false } : { toolsOpen: false }),
      setNavOpen: (navOpen) => set({ navOpen }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setCanvasSystem: (canvasSystemId) => set((state) => (state.canvasSystemId === canvasSystemId ? {} : { canvasSystemId, canvasVariant: null, chosenEntry: null, chosenProcess: null })),
      setCanvasVariant: (canvasVariant) => set({ canvasVariant }),
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
          return { details: tab, lastDetails: tab, pinned: state.pinned.map((p) => (p.id === tab.id ? tab : p)) }
        }),
      showActivity: () => set({ details: null }),
      pin: () =>
        set((state) => {
          const held = state.details
          if (held === null || state.pinned.some((p) => p.id === held.id)) return {}
          return { pinned: [...state.pinned, held] }
        }),
      unpin: (id) => set((state) => ({ pinned: state.pinned.filter((p) => p.id !== id) })),
      unpinWhere: (test) => set((state) => ({ pinned: state.pinned.filter((p) => !test(p)) })),
      toggleSection: (key) => set((state) => ({ collapsed: { ...state.collapsed, [key]: !state.collapsed[key] } })),
      toggleNavDatabase: (name) => set((state) => ({ navDatabases: { ...state.navDatabases, [name]: !state.navDatabases[name] } })),
      setFormulaValues: (shown) => set({ formulaValues: shown }),
      setScaledView: (scaledView) => set({ scaledView }),
      setMinimapOpen: (open) => set({ minimapOpen: open }),
      setExplorerScheme: (database, scheme) => set((state) => ({ explorerSchemes: { ...state.explorerSchemes, [database]: scheme } })),
      setResultCategory: (systemId, methodId) => set((state) => ({ resultCategories: { ...state.resultCategories, [systemId]: methodId } })),
    }),
    {
      name: 'ecosemantic-page',
      version: 5,
      migrate,
      merge: (persisted, current) => ({ ...current, ...(persisted as Partial<UiState>), scaledView: current.scaledView, sheetShort: current.sheetShort }),
      partialize: (state) => ({
        theme: state.theme,
        person: state.person,
        inspector: state.inspector,
        inspectorWidth: state.inspectorWidth,
        resultWidth: state.resultWidth,
        timelineOpen: state.timelineOpen,
        toolsOffset: state.toolsOffset,
        pinned: state.pinned,
        seen: state.seen,
        collapsed: state.collapsed,
        navDatabases: state.navDatabases,
        resultCategories: state.resultCategories,
        explorerSchemes: state.explorerSchemes,
        formulaValues: state.formulaValues,
        minimapOpen: state.minimapOpen,
      }),
      onRehydrateStorage: () => (state) => stamp(state?.theme ?? 'light'),
    },
  ),
)

stamp(useUi.getState().theme)
