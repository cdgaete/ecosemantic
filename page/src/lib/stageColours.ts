import type { ContributionResult } from '@/api/types'

export const STAGE_TOKENS = 6

/** The stages a split names, in the order the core gives them; the part of no stage is not one. */
export function stageNames(split: ContributionResult): string[] {
  const names: string[] = []
  for (const part of split.stages ?? []) if (part.stage !== null) names.push(part.stage)
  return names
}

/** Each own process's code and the stage of the part holding it, null for the part of no stage. */
export function stageByCode(split: ContributionResult): Map<string, string | null> {
  const stages = new Map<string, string | null>()
  for (const part of split.stages ?? [])
    for (const process of part.processes) stages.set(process.ref.code, part.stage)
  return stages
}

/** The colour of the n-th name, wrapping past the sixth token; the muted token for a part of no
 * stage or a name the split does not hold. */
export function stageColour(names: string[], stage: string | null, alpha = 1): string {
  const at = stage === null ? -1 : names.indexOf(stage)
  if (at === -1) return `rgb(var(--muted-foreground) / ${alpha})`
  return `rgb(var(--stage-${(at % STAGE_TOKENS) + 1}) / ${alpha})`
}
