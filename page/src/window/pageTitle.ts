const EXPLORER = /^\/databases\/([^/]+)(?:\/|$)/

export function pageTitle(pathname: string): string {
  if (pathname === '/') return 'Product systems'
  if (pathname === '/databases') return 'Databases'
  const explorer = EXPLORER.exec(pathname)
  if (explorer === null) return 'Not found'
  return decodeURIComponent(explorer[1])
}
