import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { useImpact, useSystem } from '@/api/queries'
import { useUi } from '@/store/ui'
import { movedSince } from '@/lib/hashes'
import { serializeParams, toImpactArguments, type ResultParams } from './params'
import { useResultParams } from './useResultParams'
import { useStartImpact } from './useStartImpact'

function useElapsed(running: boolean): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!running) return
    setSeconds(0)
    const started = Date.now()
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  return seconds
}

export function useResult() {
  const { id = '' } = useParams()
  const location = useLocation()
  const resolved = useResultParams(id, location.search)
  const params = resolved.params
  const read = useSystem(id)
  const system = read.data?.value
  const current = system?.hash ?? ''
  const [hash, setHash] = useState(current)
  useEffect(() => {
    if (hash === '' && current !== '') setHash(current)
  }, [current, hash])
  const root = system?.reference_process ?? null
  const empty: ResultParams = { variants: [], amount: 1 }
  const stale = movedSince(hash, current)
  const impact = useImpact(id, hash, toImpactArguments(params ?? empty, root), params !== null && hash !== '' && !stale, () => useUi.getState().takeStartedImpact(id))
  const seconds = useElapsed(impact.isFetching)
  const waiting = stale ? 'Recalculate to compute this page for the current model.' : `Calculating over the background database: ${seconds} s`
  const startImpact = useStartImpact(id)
  const recalculate = () => {
    setHash(current)
    startImpact(location.pathname.split('/results/')[1] ?? 'impact', resolved.callId !== null ? `?call=${resolved.callId}` : serializeParams(params ?? empty))
  }
  return { id, params, hash, system, impact, stale, waiting, recalculate, root, call: resolved.call, resolved }
}
