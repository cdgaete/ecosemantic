import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useAnchors, useCalculations, useDatabases, useRuns, useSystem, useSystems } from '@/api/queries'
import type { SystemCard } from '@/api/types'
import { beginsAWord } from '@/lib/matching'
import { distinguishingId, sharedNames } from '@/lib/names'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { groupByStage } from '@/lib/stages'
import { useUi } from '@/store/ui'
import { SECTIONS } from '@/editors/explorer/sections'
import { CanvasBadge } from './Badges'
import { Icon } from './Icon'

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
  const drawn = useAnchors(card.id, open)
  const runs = useRuns(card.id, open)
  const calculations = useCalculations(card.id, open)
  const running = (runs.data?.value ?? []).some((r) => r.open)
  const system = read.data?.value
  const openRequests = read.data?.open_requests ?? 0
  const anchors = drawn.data?.value
  const groups = system && anchors ? groupByStage(system, anchors) : []
  const waiting = drawn.error ? drawn.error.message : anchors ? null : 'Loading…'
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
          <div key={db.name}>
            <Node icon={<Icon name="database" />} label={db.name} to={paths.explorer(db.name)} depth={1} />
            {SECTIONS.map((entry) => (
              <Node
                key={entry.section}
                icon={<entry.icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />}
                label={entry.title}
                to={paths.explorer(db.name, entry.section)}
                depth={2}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
