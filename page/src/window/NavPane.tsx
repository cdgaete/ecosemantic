import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useCalculations, useDatabases, useLayout, useRuns, useSystem, useSystems } from '@/api/queries'
import type { Arrangement, ListedDatabase, Process, ProductSystem, SystemCard } from '@/api/types'
import { formatAmount } from '@/lib/format'
import { beginsAWord } from '@/lib/matching'
import { distinguishingId, sharedNames } from '@/lib/names'
import { AppLink } from '@/lib/router'
import { databaseOfPath, paths } from '@/lib/paths'
import { useUi } from '@/store/ui'
import { places } from '@/editors/explorer/sections'
import { CanvasBadge } from './Badges'
import { Icon } from './Icon'

const NO_STAGE = 'no stage'

interface StageGroup {
  stage: string
  processes: Process[]
}

/** A system's processes by the arrangement's stages, each group in its stage's order and its processes from the reference's side. */
function stageGroups(system: ProductSystem, arrangement: Arrangement): StageGroup[] {
  const rank = new Map(
    [...arrangement.cards].sort((a, b) => b.x - a.x || a.y - b.y).map((card, at) => [card.code, at] as const),
  )
  const byCode = new Map(system.processes.map((p) => [p.code, p]))
  const fromReference = (processes: Process[]) => [...processes].sort((a, b) => (rank.get(a.code) ?? Infinity) - (rank.get(b.code) ?? Infinity))
  const grouped = arrangement.stages.map((one) => ({
    stage: one.stage,
    processes: fromReference(one.codes.flatMap((code) => byCode.get(code) ?? [])),
  }))
  const staged = new Set(arrangement.stages.flatMap((one) => one.codes))
  const unstaged = fromReference(system.processes.filter((p) => !staged.has(p.code)))
  return unstaged.length > 0 ? [...grouped, { stage: NO_STAGE, processes: unstaged }] : grouped
}

function Twisty({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-label={open ? 'Collapse' : 'Expand'} className="w-3 text-muted-foreground" onClick={onClick}>
      {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
    </button>
  )
}

function Node({ icon, label, to, count, depth, twisty, note, current }: { icon: ReactNode; label: string; to?: string; count?: string; depth: number; twisty?: ReactNode; note?: string; current?: boolean }) {
  const body = (
    <>
      {icon}
      <span className="line-clamp-2 [overflow-wrap:anywhere]" title={label}>
        {label}
      </span>
      {note ? <span className="shrink-0 text-xs text-muted-foreground">{note}</span> : null}
      {current ? <CanvasBadge /> : null}
      {count ? <span className="ml-1 text-xs text-muted-foreground">{count}</span> : null}
    </>
  )
  return (
    <div className="flex items-start gap-1 py-0.5 pr-2" style={{ paddingLeft: 8 + depth * 14 }}>
      <span className="w-3">{twisty}</span>
      {to ? (
        <AppLink to={to} aria-current={current ? 'true' : undefined} className="flex min-w-0 items-start gap-1.5 rounded-sm px-1 hover:bg-selected">
          {body}
        </AppLink>
      ) : (
        <span className="flex min-w-0 items-start gap-1.5 px-1">{body}</span>
      )}
    </div>
  )
}

function SystemNode({ card, depth, shared, current }: { card: SystemCard; depth: number; shared: Set<string>; current: boolean }) {
  const [open, setOpen] = useState(false)
  const read = useSystem(card.id)
  const drawn = useLayout(card.id, null, open)
  const runs = useRuns(card.id, open)
  const calculations = useCalculations(card.id, open)
  const running = (runs.data?.value ?? []).some((r) => r.open)
  const system = read.data?.value
  const openRequests = read.data?.open_requests ?? 0
  const arrangement = drawn.data?.value
  const groups = system && arrangement ? stageGroups(system, arrangement) : []
  const waiting = drawn.error ? drawn.error.message : arrangement ? null : 'Loading…'
  return (
    <>
      <Node
        icon={<Icon name="system" />}
        label={card.name}
        note={distinguishingId(card, shared) ?? undefined}
        current={current}
        to={paths.system(card.id)}
        depth={depth}
        twisty={<Twisty open={open} onClick={() => setOpen((o) => !o)} />}
      />
      {open && system ? (
        <>
          <Node icon={<Icon name="folder" />} label="Processes" count={String(system.processes.length)} depth={depth + 1} />
          {waiting ? (
            <div className={drawn.error ? 'text-destructive' : 'text-muted-foreground'} style={{ paddingLeft: 8 + (depth + 2) * 14 }}>
              {waiting}
            </div>
          ) : null}
          {groups.map((group) => (
            <div key={group.stage}>
              <Node icon={<Icon name="folder" />} label={group.stage} depth={depth + 2} />
              {group.processes.map((p) => (
                <Node key={p.code} icon={<Icon name="process" />} label={p.name} to={paths.process(card.id, p.code)} depth={depth + 3} />
              ))}
            </div>
          ))}
          <Node icon={<Icon name="parameter" />} label="Parameters" count={String(system.parameters.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon={<Icon name="parameter" />} label="Cases" count={String(system.cases.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon={<Icon name="parameter" />} label="Scenarios" count={String(system.scenarios.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon={<Icon name="log" />} label="Log" to={paths.system(card.id)} depth={depth + 1} />
          <Node icon={<Icon name="request" />} label="Requests" count={openRequests > 0 ? `${openRequests} open` : undefined} to={paths.systemPage(card.id, 'requests')} depth={depth + 1} />
          <Node icon={<Icon name="simulation" />} label="Simulations" count={running ? 'running' : undefined} to={paths.systemPage(card.id, 'simulations')} depth={depth + 1} />
          <Node icon={<Icon name="result" />} label="Results" count={calculations.data ? String(calculations.data.value.length) : undefined} to={paths.resultList(card.id)} depth={depth + 1} />
        </>
      ) : null}
    </>
  )
}

function DatabaseNode({ database, depth }: { database: ListedDatabase; depth: number }) {
  const pathname = useLocation().pathname
  const under = databaseOfPath(pathname) === database.name
  const stored = useUi((state) => state.navDatabases[database.name])
  const toggle = useUi((state) => state.toggleNavDatabase)
  const open = under || stored === true
  return (
    <>
      <Node
        icon={<Icon name="database" />}
        label={database.name}
        to={paths.explorer(database.name)}
        count={formatAmount(database.processes)}
        depth={depth}
        twisty={<Twisty open={open} onClick={() => toggle(database.name)} />}
      />
      {open
        ? places(database.name).map((place) => (
            <Node
              key={place.key}
              icon={<place.icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />}
              label={place.title}
              to={place.to}
              depth={depth + 1}
            />
          ))
        : null}
    </>
  )
}

export function NavPane() {
  const systems = useSystems()
  const databases = useDatabases()
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  const [filter, setFilter] = useState('')
  const listed = systems.data?.value ?? []
  const shared = sharedNames(listed)
  const cards = listed.filter((c) => beginsAWord(filter, [c.name]))
  return (
    <div className="flex h-full min-w-0 flex-col bg-background text-[12.5px]">
      <input
        id="nav-filter"
        className="m-2 rounded-sm border bg-background px-1.5 py-0.5 text-xs"
        placeholder="Filter…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="min-h-0 flex-1 overflow-auto pb-2">
        <Node icon={<Icon name="system" />} label="Product systems" to={paths.home()} depth={0} count={String(cards.length)} />
        {cards.map((card) => (
          <SystemNode key={card.id} card={card} depth={1} shared={shared} current={card.id === canvasSystemId} />
        ))}
        <Node icon={<Icon name="database" />} label="Background databases" to={paths.databases()} depth={0} />
        {(databases.data?.value ?? []).map((db) => (
          <DatabaseNode key={db.name} database={db} depth={1} />
        ))}
      </div>
    </div>
  )
}
