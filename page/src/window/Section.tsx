import { ChevronDown, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { useUi } from '@/store/ui'

export function Section({ title, sectionKey, actions, children }: { title: string; sectionKey: string; actions?: ReactNode; children: ReactNode }) {
  const collapsed = useUi((s) => s.collapsed[sectionKey] ?? false)
  const toggle = useUi((s) => s.toggleSection)
  return (
    <section className="border-t px-4 py-2">
      <div className="flex items-center justify-between gap-2">
        <button type="button" className="flex items-center gap-1.5 font-semibold" aria-expanded={!collapsed} onClick={() => toggle(sectionKey)}>
          {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {title}
        </button>
        {actions ? <div className="flex items-center gap-2 text-xs">{actions}</div> : null}
      </div>
      {collapsed ? null : <div className="pt-2">{children}</div>}
    </section>
  )
}
