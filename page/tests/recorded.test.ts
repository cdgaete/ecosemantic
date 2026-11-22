import type { Call, ProductSystem } from '@/api/types'
import { heldParams, latestOf, paramsOfCall } from '@/editors/results/recorded'
import calculations from './fixtures/calculations.json'
import system from './fixtures/system.json'

const recorded = calculations.value[0] as unknown as Call
const doc = system.value as ProductSystem

it('answers the first call that succeeded and passes over one that failed', () => {
  const failed: Call = { ...recorded, id: 'failed', outcome: 'error' }
  const latest: Call = { ...recorded, id: 'latest' }
  expect(latestOf([failed, latest])?.id).toBe('latest')
  expect(latestOf([failed])).toBeUndefined()
  expect(latestOf([])).toBeUndefined()
})

it('keeps the variants the system holds and names the ones it does not', () => {
  const params = { ...paramsOfCall(recorded), variants: ['heavy', 'lighter', 'gone'] }
  const held = heldParams(params, doc)
  expect(held.params.variants).toEqual(['heavy', 'lighter'])
  expect(held.missing).toEqual(['gone'])
  expect(held.params.method_id).toBe('m_bff077f3bd')
})
