import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useAnchors, useCalculations, useDatabases, useRuns, useSystem, useSystems } from '@/api/queries'
import type { SystemCard } from '@/api/types'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { groupByStage } from '@/lib/stages'
import { Icon, type IconName } from './Icon'

function Twisty({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-label={open ? 'Collapse' : 'Expand'} className="w-3 text-muted-foreground" onClick={onClick}>
      {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
    </button>
  )
}

function Node({ icon, label, to, count, depth, twisty }: { icon: IconName; label: string; to?: string; count?: string; depth: number; twisty?: ReactNode }) {
  const body = (
    <>
      <Icon name={icon} />
      <span className="truncate">{label}</span>
      {count ? <span className="ml-1 text-xs text-muted-foreground">{count}</span> : null}
    </>
  )
  return (
    <div className="flex items-center gap-1 py-0.5 pr-2" style={{ paddingLeft: 8 + depth * 14 }}>
      <span className="w-3">{twisty}</span>
      {to ? (
        <AppLink to={to} className="flex min-w-0 items-center gap-1.5 rounded-sm px-1 hover:bg-selected">
          {body}
        </AppLink>
      ) : (
        <span className="flex min-w-0 items-center gap-1.5 px-1">{body}</span>
      )}
    </div>
  )
}

function SystemNode({ card, depth }: { card: SystemCard; depth: number }) {
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
      <Node icon="system" label={card.name} to={paths.system(card.id)} depth={depth} twisty={<Twisty open={open} onClick={() => setOpen((o) => !o)} />} />
      {open && system ? (
        <>
          <Node icon="folder" label="Processes" count={String(system.processes.length)} depth={depth + 1} />
          {waiting ? (
            <div className={drawn.error ? 'text-destructive' : 'text-muted-foreground'} style={{ paddingLeft: 8 + (depth + 2) * 14 }}>
              {waiting}
            </div>
          ) : null}
          {groups.map((group) => (
            <div key={group.stage}>
              <Node icon="folder" label={group.stage} depth={depth + 2} />
              {group.processes.map((p) => (
                <Node key={p.code} icon="process" label={p.name} to={paths.process(card.id, p.code)} depth={depth + 3} />
              ))}
            </div>
          ))}
          <Node icon="parameter" label="Parameters" count={String(system.parameters.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon="parameter" label="Cases" count={String(system.cases.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon="parameter" label="Scenarios" count={String(system.scenarios.length)} to={paths.systemPage(card.id, 'parameters')} depth={depth + 1} />
          <Node icon="log" label="Log" to={paths.system(card.id)} depth={depth + 1} />
          <Node icon="request" label="Requests" count={openRequests > 0 ? `${openRequests} open` : undefined} to={paths.systemPage(card.id, 'requests')} depth={depth + 1} />
          <Node icon="simulation" label="Simulations" count={running ? 'running' : undefined} to={paths.systemPage(card.id, 'simulations')} depth={depth + 1} />
          <Node icon="result" label="Results" count={calculations.data ? String(calculations.data.value.length) : undefined} to={paths.resultList(card.id)} depth={depth + 1} />
        </>
      ) : null}
    </>
  )
}

export function NavPane() {
  const systems = useSystems()
  const databases = useDatabases()
  const [filter, setFilter] = useState('')
  const cards = (systems.data?.value ?? []).filter((c) => c.name.toLowerCase().includes(filter.toLowerCase()))
  return (
    <aside className="flex h-full min-w-0 flex-col bg-background text-[12.5px]">
      <div className="flex items-center justify-between border-b bg-chrome px-2.5 py-1 text-xs font-semibold">Navigation</div>
      <input
        id="nav-filter"
        className="m-2 rounded-sm border bg-background px-1.5 py-0.5 text-xs"
        placeholder="Filter…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="min-h-0 flex-1 overflow-auto pb-2">
        <Node icon="system" label="Product systems" to={paths.home()} depth={0} count={String(cards.length)} />
        {cards.map((card) => (
          <SystemNode key={card.id} card={card} depth={1} />
        ))}
        <Node icon="database" label="Background databases" to={paths.databases()} depth={0} />
        {(databases.data?.value ?? []).map((db) => (
          <div key={db.name}>
            <Node icon="database" label={db.name} depth={1} />
            <Node icon="process" label="Processes" count="search" to={paths.search(db.name, 'processes')} depth={2} />
            <Node icon="elementary" label="Elementary flows" count="search" to={paths.search(db.name, 'elementary-flows')} depth={2} />
            <Node icon="result" label="Impact methods" count="search" to={paths.search(db.name, 'methods')} depth={2} />
          </div>
        ))}
      </div>
    </aside>
  )
}
