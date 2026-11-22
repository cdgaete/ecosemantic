import { useCalculations, useContributions, useImpact, useSystem } from '@/api/queries'
import type { Call, ContributionArguments, ContributionResult, Method, Score } from '@/api/types'
import { useCategory } from '@/lib/address'
import { hashLine } from '@/lib/hashes'
import { useCanvasVariant, type CanvasVariant } from '@/window/useCanvasState'
import { demandOf, type ResultParams, toImpactArguments } from './params'
import { heldParams, latestOf, paramsOfCall, variantsOf } from './recorded'

export interface BandCase {
  name: string | null
  score: number | null
  held: boolean
}

export interface Band {
  call: Call
  params: ResultParams
  cases: BandCase[]
  categories: Score[]
  methods: Method[]
  chosen: Score | undefined
  choose: (id: string) => void
  variant: string | null
  unscored: CanvasVariant | null
  hashLine: string | null
  split: ContributionResult | undefined
}

/** The system's latest successful calculation scored on the current model, with every case it scored,
 * its categories and the split by stage of the chosen one, or null while it has no such calculation or
 * while `enabled` is false, where it asks the server nothing. */
export function useBand(systemId: string, enabled = true): Band | null {
  const system = useSystem(systemId).data?.value
  const call = latestOf(useCalculations(systemId, enabled).data?.value ?? [])
  const held = call === undefined || system === undefined ? null : heldParams(paramsOfCall(call), system)
  const root = system?.reference_process ?? null
  const hash = system?.hash ?? ''
  const body = held === null ? { variants: [] } : toImpactArguments(held.params, root)
  const impact = useImpact(systemId, hash, body, enabled && held !== null)
  const scores = impact.data?.value.scores ?? []
  const methods = impact.data?.value.methods ?? []
  const answers = impact.data?.value.variants ?? []
  const { chosen, choose } = useCategory(scores, systemId, (category) => category.value)
  const canvas = useCanvasVariant(system)
  const scored = canvas !== null && call !== undefined && variantsOf(call).includes(canvas.name)
  const variant = scored ? canvas.name : null
  const unscored = canvas !== null && !scored ? canvas : null
  const demand = held === null ? undefined : demandOf(held.params, root)
  const splitBody: ContributionArguments = {
    by: 'stage',
    ...(chosen === undefined ? {} : { method_id: chosen.method_id }),
    ...(demand === undefined ? {} : { demand }),
    ...(variant === null ? {} : { variant }),
  }
  const split = useContributions(systemId, hash, splitBody, enabled && chosen !== undefined)
  if (!enabled || call === undefined || system === undefined || held === null) return null
  const cases: BandCase[] = [
    {
      name: null,
      score: chosen === undefined ? null : (scores.find((score) => score.method_id === chosen.method_id)?.value ?? null),
      held: true,
    },
    ...variantsOf(call).map((name) => {
      const kept = !held.missing.includes(name)
      const answered = answers.find((answer) => answer.name === name)
      const score = answered === undefined || chosen === undefined ? null : (answered.scores.find((one) => one.method_id === chosen.method_id)?.value ?? null)
      return { name, score: kept ? score : null, held: kept }
    }),
  ]
  return {
    call,
    params: held.params,
    cases,
    categories: scores,
    methods,
    chosen,
    choose,
    variant,
    unscored,
    hashLine: hashLine(call.at_hash, system.hash),
    split: split.data?.value,
  }
}
