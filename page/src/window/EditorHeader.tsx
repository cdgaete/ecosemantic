import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import { StateLine } from './StateLine'
import type { CanvasVariant } from './useCanvasState'

export function EditorHeader({ icon, page, entity, state, actions }: { icon: IconName; page: string; entity: string; state?: CanvasVariant | null; actions?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-2">
      <div className="flex min-w-0 flex-col gap-0.5">
        <h1 className="flex items-center gap-2 text-base font-semibold">
          <Icon name={icon} />
          <span>
            {page} – {entity}
          </span>
        </h1>
        <StateLine state={state ?? null} />
      </div>
      {actions ? <div className="flex items-center gap-2 text-xs">{actions}</div> : null}
    </div>
  )
}
