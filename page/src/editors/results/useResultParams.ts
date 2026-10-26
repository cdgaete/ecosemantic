import { useCalculations } from '@/api/queries'
import type { Call } from '@/api/types'
import { callOf, parseParams, type ResultParams } from './params'
import { paramsOfCall } from './recorded'

export interface ResolvedParams {
  params: ResultParams | null
  call: Call | null
  callId: string | null
  waiting: boolean
  error: Error | null
}

export function useResultParams(id: string, search: string): ResolvedParams {
  const callId = callOf(search)
  const calculations = useCalculations(id, callId !== null && id !== '')
  if (callId === null) return { params: parseParams(search), call: null, callId, waiting: false, error: null }
  const call = calculations.data?.value.find((c) => c.id === callId) ?? null
  return { params: call ? paramsOfCall(call) : null, call, callId, waiting: calculations.isPending, error: calculations.error }
}
