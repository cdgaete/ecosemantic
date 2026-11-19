import { databaseOfPath } from '@/lib/paths'

export function pageTitle(pathname: string): string {
  if (pathname === '/') return 'Product systems'
  if (pathname === '/databases') return 'Databases'
  return databaseOfPath(pathname) ?? 'Not found'
}
