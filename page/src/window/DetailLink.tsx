import type { MouseEvent } from 'react'
import type { LinkProps } from 'react-router-dom'
import { AppLink } from '@/lib/router'
import { openInspector } from './inspector'

function deliberate(event: MouseEvent<HTMLAnchorElement>): boolean {
  return !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
}

/**
 * A link to something the inspector shows. A deliberate activation shows the inspector again, so a second click on the
 * address already open reopens one that was closed; a modified or non-primary activation is left to the browser and
 * changes nothing in this tab.
 */
export function DetailLink({ to, ...rest }: Omit<LinkProps, 'to' | 'onClick'> & { to: string }) {
  return (
    <AppLink
      to={to}
      {...rest}
      onClick={(event) => {
        if (deliberate(event)) openInspector()
      }}
    />
  )
}
