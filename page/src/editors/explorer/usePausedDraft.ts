import { useEffect, useRef, useState } from 'react'

export const FILTER_PAUSE_MS = 300

export interface PausedDraft {
  draft: string
  type: (next: string) => void
  settle: () => string
}

/** A field's text as it is typed, handed on once the typing pauses; settle hands it on at once. */
export function usePausedDraft(value: string, onChange: (value: string) => void): PausedDraft {
  const [draft, setDraft] = useState(value)
  const sent = useRef(value)
  const pause = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latest = useRef(onChange)
  useEffect(() => {
    latest.current = onChange
  })
  useEffect(() => {
    if (value === sent.current) return
    if (pause.current !== null) clearTimeout(pause.current)
    pause.current = null
    sent.current = value
    setDraft(value)
  }, [value])
  useEffect(
    () => () => {
      if (pause.current !== null) clearTimeout(pause.current)
    },
    [],
  )
  const type = (next: string) => {
    setDraft(next)
    if (pause.current !== null) clearTimeout(pause.current)
    pause.current = setTimeout(() => {
      pause.current = null
      sent.current = next
      latest.current(next)
    }, FILTER_PAUSE_MS)
  }
  const settle = () => {
    if (pause.current !== null) clearTimeout(pause.current)
    pause.current = null
    sent.current = draft
    return draft
  }
  return { draft, type, settle }
}
