import type { MethodFamily } from '@/api/types'
import { Tree, type TreeNode } from './Tree'

export function MethodTree({
  families,
  family,
  category,
  onOpen,
}: {
  families: MethodFamily[]
  family: string
  category: string
  onOpen: (family: string, category: string | null) => void
}) {
  const places = new Map<string, { family: string; category: string | null }>()
  const nodes: TreeNode[] = families.map((entry) => {
    const familyId = `f:${entry.name}`
    places.set(familyId, { family: entry.name, category: null })
    return {
      id: familyId,
      label: entry.name,
      note: null,
      count: null,
      children: entry.categories.map((child) => {
        const id = `c:${entry.name}\n${child.name}`
        places.set(id, { family: entry.name, category: child.name })
        return { id, label: child.name, note: null, count: null, children: [] }
      }),
    }
  })
  const open = category !== '' ? `c:${family}\n${category}` : family !== '' ? `f:${family}` : ''
  return (
    <Tree
      label="Impact methods"
      subject="family"
      nodes={nodes}
      open={open}
      onOpen={(id) => {
        const place = places.get(id)
        if (place === undefined) return
        onOpen(place.family, place.category)
      }}
    />
  )
}
