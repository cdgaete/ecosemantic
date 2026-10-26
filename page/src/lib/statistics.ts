import type { ProductSystem } from '@/api/types'

export function countStatistics(system: ProductSystem): { processes: number; foregroundLinks: number; backgroundLinks: number; parameters: number } {
  const exchanges = system.processes.flatMap((p) => p.exchanges)
  return {
    processes: system.processes.length,
    foregroundLinks: exchanges.filter((e) => e.input?.kind === 'foreground').length,
    backgroundLinks: exchanges.filter((e) => e.input?.kind === 'background').length,
    parameters: system.parameters.length,
  }
}
