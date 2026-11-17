import type { Compartment } from '@/api/types'
import { Tree, type TreeNode } from './Tree'

export function CompartmentTree({
  compartments,
  compartment,
  sub,
  onOpen,
}: {
  compartments: Compartment[]
  compartment: string
  sub: string
  onOpen: (compartment: string, sub: string | null) => void
}) {
  const places = new Map<string, { compartment: string; sub: string | null }>()
  const nodes: TreeNode[] = compartments.map((entry) => {
    places.set(entry.name, { compartment: entry.name, sub: null })
    return {
      id: entry.name,
      label: entry.name,
      note: null,
      count: entry.flow_count,
      children: entry.sub_compartments.map((child) => {
        const id = `${entry.name}\n${child.name}`
        places.set(id, { compartment: entry.name, sub: child.name })
        return { id, label: child.name, note: null, count: child.flow_count, children: [] }
      }),
    }
  })
  const open = sub === '' ? compartment : `${compartment}\n${sub}`
  return (
    <Tree
      label="Compartments"
      subject="compartment"
      nodes={nodes}
      open={open}
      onOpen={(id) => {
        const place = places.get(id)
        if (place === undefined) return
        onOpen(place.compartment, place.sub)
      }}
    />
  )
}
