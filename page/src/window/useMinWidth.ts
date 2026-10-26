import { useEffect, useState } from 'react'

export function useMinWidth(px: number): boolean {
  const media = `(min-width: ${px}px)`
  const [matches, setMatches] = useState(() => window.matchMedia(media).matches)
  useEffect(() => {
    const query = window.matchMedia(media)
    const onChange = () => setMatches(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [media])
  return matches
}
