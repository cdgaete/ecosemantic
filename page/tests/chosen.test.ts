import { chosenRefs, refKey } from '@/activity/chosen'
import type { Call } from '@/api/types'
import trail from './fixtures/trail.json'

const calls = trail.value as unknown as Call[]

describe('chosen candidates', () => {
  it('marks the reference a later write of the trail took as its input', () => {
    const found = calls[0].summary?.items[0]
    expect(found).toBeDefined()
    expect(chosenRefs(calls, 0)).toEqual(new Set([refKey(found?.database ?? null, found?.ref ?? null)]))
  })

  it('marks nothing after the write', () => {
    expect(chosenRefs(calls, calls.length - 1).size).toBe(0)
  })
})
