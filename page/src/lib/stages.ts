import type { Process, ProductSystem } from '@/api/types'

export interface StageGroup {
  stage: string
  processes: Process[]
}

export const NO_STAGE = 'no stage'

export function stageOf(process: Process): string {
  const stage = process.metadata['life_cycle_stage']
  return typeof stage === 'string' && stage.length > 0 ? stage : NO_STAGE
}

function localProviders(process: Process): string[] {
  return process.exchanges.flatMap((e) => (e.input && e.input.kind === 'foreground' ? [e.input.code] : []))
}

export function walkOrder(system: ProductSystem, anchors: string[]): Process[] {
  const byCode = new Map(system.processes.map((p) => [p.code, p]))
  const seen = new Set<string>()
  const ordered: Process[] = []
  const queue = [...anchors]
  while (queue.length > 0) {
    const code = queue.shift()!
    const process = byCode.get(code)
    if (!process || seen.has(code)) continue
    seen.add(code)
    ordered.push(process)
    queue.push(...localProviders(process))
  }
  for (const process of byCode.values()) if (!seen.has(process.code)) ordered.push(process)
  return ordered
}

export function stageOrder(system: ProductSystem, anchors: string[]): string[] {
  const order: string[] = []
  for (const process of walkOrder(system, anchors)) {
    const stage = stageOf(process)
    if (!order.includes(stage)) order.push(stage)
  }
  const named = order.filter((s) => s !== NO_STAGE)
  return order.includes(NO_STAGE) ? [...named, NO_STAGE] : named
}

export function groupByStage(system: ProductSystem, anchors: string[]): StageGroup[] {
  return stageOrder(system, anchors).map((stage) => ({
    stage,
    processes: system.processes.filter((p) => stageOf(p) === stage),
  }))
}
