import { useEffect, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { useImpact, useSystem } from '@/api/queries'
import type { ImpactArguments } from '@/api/types'
import { useUi } from '@/store/ui'
import { useCanvasVariant, heldVariant } from '@/window/useCanvasState'
import { movedSince } from '@/lib/hashes'
import { serializeParams, toImpactArguments, variantOf, type ResultParams } from './params'
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
  const addressed = variantOf(location.search)
  const addressedVariant = system === undefined ? null : heldVariant(system, addressed)
  const missingCase = addressed !== null && system !== undefined && addressedVariant === null ? addressed : null
  const canvasSystemId = useUi((s) => s.canvasSystemId)
  const setCanvasVariant = useUi((s) => s.setCanvasVariant)
  const chosen = useRef<string | null>(null)
  useEffect(() => {
    if (addressed === null || canvasSystemId !== id) return
    if (chosen.current === location.search) return
    chosen.current = location.search
    setCanvasVariant(addressed)
  }, [addressed, canvasSystemId, id, location.search, setCanvasVariant])
  const state = useCanvasVariant(system)
  const body = toImpactArguments(params ?? empty, root)
  const held = addressedVariant !== null && !(body.variants ?? []).includes(addressedVariant.name) ? addressedVariant.name : null
  const argumentsOf: ImpactArguments = held === null ? body : { ...body, variants: [...(body.variants ?? []), held] }
  const impact = useImpact(id, hash, argumentsOf, params !== null && hash !== '' && !stale, () => useUi.getState().takeStartedImpact(id))
  const seconds = useElapsed(impact.isFetching)
  const waiting = stale ? 'Recalculate to compute this page for the current model.' : `Calculating over the background database: ${seconds} s`
  const startImpact = useStartImpact(id)
  const recalculate = () => {
    setHash(current)
    startImpact(location.pathname.split('/results/')[1] ?? 'impact', resolved.callId !== null ? `?call=${resolved.callId}` : serializeParams(params ?? empty))
  }
  return { id, params, hash, system, impact, stale, waiting, recalculate, root, call: resolved.call, resolved, state, variant: state?.name ?? null, missingCase }
}
