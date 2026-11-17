import type { ClassificationNode } from '@/api/types'
import { Tree, type TreeNode } from './Tree'

function nodesOf(nodes: ClassificationNode[]): TreeNode[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.label,
    note: node.name,
    count: node.processes,
    children: nodesOf(node.children),
  }))
}

export function ClassificationTree({ nodes, open, onOpen }: { nodes: ClassificationNode[]; open: string; onOpen: (id: string) => void }) {
  return <Tree label="Classification" subject="node of the classification" nodes={nodesOf(nodes)} open={open} onOpen={onOpen} />
}
