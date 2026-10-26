import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useParams } from 'react-router-dom'
import { keys, useImpact, useSystem } from '@/api/queries'
import { useUi } from '@/store/ui'
import { paths, useGo } from '@/lib/paths'
import { serializeParams, toImpactArguments, type ResultParams } from './params'
import { useResultParams } from './useResultParams'

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
  const go = useGo()
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
  const stale = current !== '' && hash !== '' && current !== hash
  const impact = useImpact(id, hash, toImpactArguments(params ?? empty, root), params !== null && hash !== '' && !stale, () => useUi.getState().takeStartedImpact(id))
  const seconds = useElapsed(impact.isFetching)
  const waiting = stale ? 'Recalculate to compute this page for the current model.' : `Calculating over the background database: ${seconds} s`
  const client = useQueryClient()
  const recalculate = () => {
    useUi.getState().startImpact(id)
    client.removeQueries({ queryKey: keys.impacts(id) })
    setHash(current)
    go(paths.results(id, location.pathname.split('/results/')[1] ?? 'impact', resolved.callId !== null ? `?call=${resolved.callId}` : serializeParams(params ?? empty)))
  }
  return { id, params, hash, system, impact, stale, waiting, recalculate, root, call: resolved.call, resolved }
}
