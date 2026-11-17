import { TIMELINE_CARD, timelineFits } from '@/activity/timeline'

it('gives a timeline card its width with the gap beside it', () => {
  expect(TIMELINE_CARD).toBe(216)
})

it('fits as many cards as the width holds, and one at least', () => {
  expect(timelineFits(0)).toBe(1)
  expect(timelineFits(215)).toBe(1)
  expect(timelineFits(640)).toBe(3)
  expect(timelineFits(1048)).toBe(4)
})
