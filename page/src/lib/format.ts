import type { Method } from '@/api/types'

export function formatAmount(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (magnitude >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  if (magnitude >= 0.001) return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  if (magnitude === 0) return '0'
  return value.toExponential(2)
}

export function formatShare(fraction: number): string {
  return `${(100 * fraction).toFixed(1)} %`
}

export function shortHash(hash: string | null): string {
  if (hash === null) return ''
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`
}

export function creditLoopNote(codes: string[], variant?: string): string {
  const loop = `the loop through ${codes.join(', ')} holds a credit; whether it delivers what it makes is not checked.`
  return variant === undefined ? `${loop[0].toUpperCase()}${loop.slice(1)}` : `In ${variant}, ${loop}`
}

export function backwardsTreatmentNote(named: string, variant?: string): string {
  const sent = `${named} sends a positive amount to a treatment, which runs it backwards and counts its emissions as credits; waste goes to a treatment as a negative input.`
  return variant === undefined ? sent : `In ${variant}, ${sent}`
}

export function categoryLabel(method: Method): string {
  return method.indicator ? `${method.impact_category} · ${method.indicator}` : method.impact_category
}

export function formatAgo(instant: string, now: Date = new Date()): string {
  const seconds = Math.floor((now.getTime() - new Date(instant).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  return instant.slice(0, 10)
}
