import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { formatAmount } from '@/lib/format'
import { cn } from '@/lib/utils'
import { IconButton } from '@/window/IconButton'

export interface TreeNode {
  id: string
  label: string
  note: string | null
  count: number | null
  children: TreeNode[]
}

function holds(node: TreeNode, term: string): boolean {
  if (term === '') return true
  if (node.label.toLocaleLowerCase().includes(term)) return true
  if (node.note !== null && node.note.toLocaleLowerCase().includes(term)) return true
  return node.children.some((child) => holds(child, term))
}

function Branch({
  node,
  depth,
  open,
  term,
  expanded,
  onOpen,
  onToggle,
}: {
  node: TreeNode
  depth: number
  open: string
  term: string
  expanded: Record<string, boolean>
  onOpen: (node: TreeNode) => void
  onToggle: (id: string) => void
}) {
  const kept = term === '' ? node.children : node.children.filter((child) => holds(child, term))
  const branching = kept.length > 0
  const shown = term !== '' || (expanded[node.id] ?? false)
  return (
    <li className="min-w-0">
      <div className="flex min-w-0 items-center" style={{ paddingLeft: depth * 12 }}>
        {branching && term === '' ? (
          <IconButton label={`${shown ? 'Collapse' : 'Expand'} ${node.label}`} onClick={() => onToggle(node.id)}>
            {shown ? <ChevronDown /> : <ChevronRight />}
          </IconButton>
        ) : branching ? (
          <span className="flex size-7 shrink-0 items-center justify-center text-muted-foreground">
            <ChevronDown className="size-4" />
          </span>
        ) : (
          <span className="size-7 shrink-0" />
        )}
        <button
          type="button"
          aria-current={open === node.id ? 'true' : undefined}
          className={cn(
            'flex min-w-0 flex-1 items-baseline gap-1.5 rounded-md px-1.5 py-1 text-left text-xs hover:bg-foreground/8',
            open === node.id && 'bg-selected text-foreground',
          )}
          onClick={() => onOpen(node)}
        >
          <span className={cn('tabular-nums', node.note === null ? 'min-w-0 [overflow-wrap:anywhere]' : 'shrink-0')}>{node.label}</span>{' '}
          {node.note === null ? null : (
            <>
              <span className="min-w-0 text-muted-foreground [overflow-wrap:anywhere]">{node.note}</span>{' '}
            </>
          )}
          {node.count === null ? null : <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">{formatAmount(node.count)}</span>}
        </button>
      </div>
      {branching && shown ? (
        <ul className="min-w-0">
          {kept.map((child) => (
            <Branch key={child.id} node={child} depth={depth + 1} open={open} term={term} expanded={expanded} onOpen={onOpen} onToggle={onToggle} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export function Tree({
  label,
  subject,
  nodes,
  open,
  onOpen,
}: {
  label: string
  subject: string
  nodes: TreeNode[]
  open: string
  onOpen: (id: string) => void
}) {
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const term = filter.trim().toLocaleLowerCase()
  const shown = nodes.filter((node) => holds(node, term))
  const toggle = (id: string) => setExpanded((state) => ({ ...state, [id]: !(state[id] ?? false) }))
  const openNode = (node: TreeNode) => {
    if (node.children.length > 0) setExpanded((state) => ({ ...state, [node.id]: true }))
    onOpen(node.id)
  }
  return (
    <nav aria-label={label} className="min-w-0 pt-2">
      <label htmlFor="explorer-tree-filter" className="block text-xs text-muted-foreground">
        Filter the tree
      </label>
      <input
        id="explorer-tree-filter"
        className="mt-0.5 w-full min-w-0 rounded-sm border bg-background px-1.5 py-0.5 text-xs"
        placeholder="Filter…"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />
      <ul className="min-w-0 pt-1">
        {shown.map((node) => (
          <Branch key={node.id} node={node} depth={0} open={open} term={term} expanded={expanded} onOpen={openNode} onToggle={toggle} />
        ))}
      </ul>
      {shown.length === 0 ? (
        <p className="pt-1 text-xs text-muted-foreground">{filter === '' ? `This database lists no ${subject}.` : `No ${subject} holds “${filter}”.`}</p>
      ) : null}
    </nav>
  )
}
