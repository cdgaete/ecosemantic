import { countStatistics } from '@/lib/statistics'
import system from './fixtures/system.json'
import type { ProductSystem } from '@/api/types'

it('counts what the document holds', () => {
  const doc = system.value as ProductSystem
  const counts = countStatistics(doc)
  expect(counts.processes).toBe(doc.processes.length)
  expect(counts.parameters).toBe(doc.parameters.length)
  expect(counts.foregroundLinks).toBe(1)
  expect(counts.backgroundLinks).toBe(doc.processes.flatMap((p) => p.exchanges).filter((e) => e.input?.kind === 'background').length)
})
