import { Fragment } from 'react'
import { useSystem } from '@/api/queries'
import { AppLink } from '@/lib/router'
import { paths } from '@/lib/paths'
import { useUi } from '@/store/ui'

export function Breadcrumb() {
  const systemId = useUi((s) => s.canvasSystemId)
  const trail = useUi((s) => s.trail)
  const read = useSystem(systemId ?? '', systemId !== null)
  if (systemId === null && trail.length === 0) return null
  const steps = trail.slice(trail.findIndex((step) => step.id === `system:${systemId}`) + 1)
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 overflow-x-auto border-t bg-chrome px-2.5 py-0.5 text-[11.5px] whitespace-nowrap text-muted-foreground">
      <AppLink to={paths.home()} className="hover:underline">
        Product systems
      </AppLink>
      {systemId ? (
        <>
          <span>›</span>
          <AppLink to={paths.system(systemId)} className="hover:underline">
            {read.data?.value.name ?? 'Product system'}
          </AppLink>
        </>
      ) : null}
      {steps.map((step) => (
        <Fragment key={step.id}>
          <span>›</span>
          <AppLink to={step.path} className="max-w-64 truncate hover:underline" title={step.title}>
            {step.title}
          </AppLink>
        </Fragment>
      ))}
    </nav>
  )
}
