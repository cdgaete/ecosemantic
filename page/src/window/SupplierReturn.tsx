import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useGo } from '@/lib/paths'
import { cn } from '@/lib/utils'
import { useSupplierOrigin } from './supplier'

/** The button that returns to the process whose exchange led here, at the top of a detail followed from one. */
export function SupplierReturn({ className }: { className?: string }) {
  const origin = useSupplierOrigin()
  const go = useGo()
  if (origin === null) return null
  return (
    <div className={cn('flex min-w-0', className)}>
      <Button
        size="sm"
        variant="ghost"
        className="mb-1 h-auto min-h-7 max-w-full shrink gap-1 px-2 py-1 text-left text-xs whitespace-normal"
        onClick={() => go(origin.address, { supplierOrigin: origin.under, supplierReturn: { scroll: origin.scroll, exchange: origin.exchange } })}
      >
        <ArrowLeft /> {`Back to ${origin.name}`}
      </Button>
    </div>
  )
}
