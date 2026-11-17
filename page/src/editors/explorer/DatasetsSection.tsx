import { useEffect } from 'react'
import { useSchemes, useTree } from '@/api/queries'
import type { ClassificationNode } from '@/api/types'
import { useAddress } from '@/lib/address'
import { useUi } from '@/store/ui'
import { ClassificationTree } from './ClassificationTree'
import { ExplorerColumns } from './ExplorerColumns'
import { ShowTree } from './ListingControls'
import { ProcessDetail } from './ProcessDetail'
import { ProcessTable } from './ProcessTable'

function findValue(nodes: ClassificationNode[], value: string): ClassificationNode | null {
  for (const node of nodes) {
    if (node.value === value) return node
    const found = findValue(node.children, value)
    if (found !== null) return found
  }
  return null
}

function findNode(nodes: ClassificationNode[], id: string): ClassificationNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = findNode(node.children, id)
    if (found !== null) return found
  }
  return null
}

export function DatasetsSection({ name }: { name: string }) {
  const address = useAddress()
  const item = address.read('item')
  const wide = address.read('wide') === '1'
  const schemes = useSchemes(name)
  const listed = schemes.data?.value ?? []
  const remembered = useUi((state) => state.explorerSchemes[name])
  const setExplorerScheme = useUi((state) => state.setExplorerScheme)
  const asked = address.read('scheme')
  const scheme =
    listed.find((entry) => entry.scheme === asked)?.scheme ?? listed.find((entry) => entry.scheme === remembered)?.scheme ?? listed[0]?.scheme ?? null
  const tree = useTree(name, scheme)
  const nodes = tree.data?.value ?? []
  const nodeId = address.read('node')
  const wanted = address.read('value')
  useEffect(() => {
    if (wanted === '' || nodeId !== '' || tree.data === undefined) return
    const found = findValue(tree.data.value, wanted)
    if (found !== null) address.write({ node: found.id, value: undefined })
  }, [wanted, nodeId, tree.data, address])
  if (schemes.error) return <p className="p-3 text-destructive">{schemes.error.message}</p>
  if (schemes.data === undefined) return <p className="p-3 text-muted-foreground">Loading…</p>
  if (listed.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <p className="pb-2 text-xs text-muted-foreground">This database carries no classification. Search the whole database instead.</p>
        <ProcessTable name={name} scheme={null} node={null} everywhere />
      </div>
    )
  }
  const node = nodeId === '' ? null : findNode(nodes, nodeId)
  const unmatched = wanted !== '' && nodeId === '' && tree.data !== undefined && findValue(tree.data.value, wanted) === null
  return (
    <ExplorerColumns
      open={item !== '' || nodeId !== ''}
      wide={wide}
      tree={
        <>
          <label htmlFor="explorer-scheme" className="block text-xs text-muted-foreground">
            Scheme
          </label>
          <select
            id="explorer-scheme"
            className="mt-0.5 w-full min-w-0 rounded-sm border bg-background px-1 py-0.5 text-xs"
            value={scheme ?? ''}
            onChange={(event) => {
              const chosen = event.target.value
              setExplorerScheme(name, chosen)
              address.write({ scheme: chosen, node: undefined, value: undefined, cursor: undefined, whole: undefined })
            }}
          >
            {listed.map((entry) => (
              <option key={entry.scheme} value={entry.scheme}>
                {entry.scheme}
              </option>
            ))}
          </select>
          <ClassificationTree
            nodes={nodes}
            open={nodeId}
            onOpen={(chosen) => address.write({ node: chosen, scheme: scheme ?? undefined, value: undefined, cursor: undefined, whole: undefined })}
          />
        </>
      }
      table={
        <>
          {nodeId === '' ? null : (
            <ShowTree onClick={() => address.write({ node: undefined, item: undefined, cursor: undefined, whole: undefined })} />
          )}
          {unmatched ? (
            <p className="text-xs text-muted-foreground">
              No node of {scheme} carries the value “{wanted}”.
            </p>
          ) : (
            <ProcessTable name={name} scheme={scheme} node={node} />
          )}
        </>
      }
      detail={item === '' ? null : <ProcessDetail key={item} name={name} item={item} />}
    />
  )
}
