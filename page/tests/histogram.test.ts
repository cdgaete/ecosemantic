import { bins } from '@/lib/histogram'

it('bins samples into equal widths covering the range', () => {
  const out = bins([1, 2, 2, 3, 4, 10], 3)
  expect(out).toHaveLength(3)
  expect(out[0].x0).toBe(1)
  expect(out[2].x1).toBe(10)
  expect(out.reduce((n, b) => n + b.n, 0)).toBe(6)
  expect(bins([], 5)).toEqual([])
  for (const b of out) expect(b.x0).toBeLessThanOrEqual(b.x1)
})

it('collapses to a single, non-inverted bin when every sample shares one value', () => {
  expect(bins([5], 24)).toEqual([{ x0: 5, x1: 5, n: 1 }])
  expect(bins([2, 2, 2, 2], 5)).toEqual([{ x0: 2, x1: 2, n: 4 }])
})
