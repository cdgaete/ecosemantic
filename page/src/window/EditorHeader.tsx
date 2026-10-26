import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

export function EditorHeader({ icon, page, entity, actions }: { icon: IconName; page: string; entity: string; actions?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-2">
      <h1 className="flex items-center gap-2 text-base font-semibold">
        <Icon name={icon} />
        <span>
          {page} – {entity}
        </span>
      </h1>
      {actions ? <div className="flex items-center gap-2 text-xs">{actions}</div> : null}
    </div>
  )
}
