import { useEffect } from 'react'
import { useMethodTree } from '@/api/queries'
import { useAddress } from '@/lib/address'
import { ExplorerColumns } from './ExplorerColumns'
import { IndicatorDetail } from './IndicatorDetail'
import { IndicatorTable } from './IndicatorTable'
import { ShowTree } from './ListingControls'
import { findIndicator } from './methods'
import { MethodTree } from './MethodTree'

export function MethodsSection({ name }: { name: string }) {
  const address = useAddress()
  const item = address.read('item')
  const wide = address.read('wide') === '1'
  const read = useMethodTree(name)
  const asked = address.read('family')
  useEffect(() => {
    if (item === '' || asked !== '' || read.data === undefined) return
    const found = findIndicator(read.data.value, item)
    if (found === null) return
    address.write({ family: found.family.name, category: found.category.name })
  }, [item, asked, read.data, address])
  if (read.error) return <p className="p-3 text-destructive">{read.error.message}</p>
  if (read.data === undefined) return <p className="p-3 text-muted-foreground">Loading…</p>
  const families = read.data.value
  const family = families.find((entry) => entry.name === asked) ?? null
  const category = family?.categories.find((entry) => entry.name === address.read('category')) ?? null
  return (
    <ExplorerColumns
      open={family !== null || item !== ''}
      wide={wide}
      tree={
        <MethodTree
          families={families}
          family={family?.name ?? ''}
          category={category?.name ?? ''}
          onOpen={(chosen, chosenCategory) =>
            address.write({
              family: chosen,
              category: chosenCategory ?? undefined,
              cursor: undefined,
              whole: undefined,
              item: undefined,
            })
          }
        />
      }
      table={
        <>
          {family === null ? null : (
            <ShowTree onClick={() => address.write({ family: undefined, category: undefined, item: undefined, cursor: undefined, whole: undefined })} />
          )}
          <IndicatorTable name={name} family={family} category={category} />
        </>
      }
      detail={item === '' ? null : <IndicatorDetail key={item} name={name} item={item} />}
    />
  )
}
