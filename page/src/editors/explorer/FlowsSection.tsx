import { useCompartmentList } from '@/api/queries'
import { useAddress } from '@/lib/address'
import { CompartmentTree } from './CompartmentTree'
import { ExplorerColumns } from './ExplorerColumns'
import { FlowDetail } from './FlowDetail'
import { FlowTable } from './FlowTable'
import { ShowTree } from './ListingControls'

export function FlowsSection({ name }: { name: string }) {
  const address = useAddress()
  const item = address.read('item')
  const wide = address.read('wide') === '1'
  const read = useCompartmentList(name)
  if (read.error) return <p className="p-3 text-destructive">{read.error.message}</p>
  if (read.data === undefined) return <p className="p-3 text-muted-foreground">Loading…</p>
  const compartments = read.data.value
  const asked = address.read('compartment')
  const compartment = compartments.find((entry) => entry.name === asked) ?? null
  const sub = compartment?.sub_compartments.find((entry) => entry.name === address.read('sub')) ?? null
  return (
    <ExplorerColumns
      open={compartment !== null || item !== ''}
      wide={wide}
      tree={
        <CompartmentTree
          compartments={compartments}
          compartment={compartment?.name ?? ''}
          sub={sub?.name ?? ''}
          onOpen={(chosen, chosenSub) =>
            address.write({
              compartment: chosen,
              sub: chosenSub ?? undefined,
              cursor: undefined,
              whole: undefined,
              item: undefined,
            })
          }
        />
      }
      table={
        <>
          {compartment === null ? null : (
            <ShowTree onClick={() => address.write({ compartment: undefined, sub: undefined, item: undefined, cursor: undefined, whole: undefined })} />
          )}
          <FlowTable name={name} compartment={compartment} sub={sub} />
        </>
      }
      detail={item === '' ? null : <FlowDetail key={item} name={name} item={item} />}
    />
  )
}
