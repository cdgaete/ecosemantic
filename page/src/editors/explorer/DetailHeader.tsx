import { Maximize2, Minimize2 } from 'lucide-react'
import { useAddress } from '@/lib/address'
import { IconButton } from '@/window/IconButton'

export function DetailHeader({ title }: { title: string }) {
  const address = useAddress()
  const wide = address.read('wide') === '1'
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 pb-1">
      <h2 className="min-w-0 text-sm font-semibold [overflow-wrap:anywhere]">{title}</h2>
      <button type="button" className="text-xs text-accent" onClick={() => address.write({ item: undefined })}>
        Show the listing
      </button>
      <div className="ml-auto hidden items-center gap-1 @5xl:flex">
        {wide ? (
          <IconButton label="Give the space back" onClick={() => address.write({ wide: undefined })}>
            <Minimize2 />
          </IconButton>
        ) : (
          <IconButton label="Take the table's space" onClick={() => address.write({ wide: '1' })}>
            <Maximize2 />
          </IconButton>
        )}
      </div>
    </div>
  )
}
