import { useLocation } from 'react-router-dom'

export function NoEditor() {
  const location = useLocation()
  return <p className="p-4 text-sm text-muted-foreground">This page has no editor for {location.pathname}.</p>
}
