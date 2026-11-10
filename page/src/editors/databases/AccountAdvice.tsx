import type { ReactNode } from 'react'
import type { AccountEntry } from '@/api/types'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export const KEPT = 'Kept on this computer until EcoSemantic restarts.'

export function AccountAdvice({ entry, children }: { entry: AccountEntry; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="flex min-w-0 flex-col gap-2">
            {children}
          </span>
        </TooltipTrigger>
        <TooltipContent>{entry.why}</TooltipContent>
      </Tooltip>
      <p className="break-words text-muted-foreground">{entry.steps}</p>
    </div>
  )
}
