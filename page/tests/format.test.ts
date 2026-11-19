import type { Method } from '@/api/types'
import { categoryLabel, cutNotice, formatAmount, formatAgo, formatShare, methodById, methodLabel, shortHash } from '@/lib/format'

describe('formatAmount', () => {
  it('rounds by magnitude', () => {
    expect(formatAmount(1234.5)).toBe('1,235')
    expect(formatAmount(1.23456)).toBe('1.23')
    expect(formatAmount(0.012345)).toBe('0.0123')
    expect(formatAmount(0.0005)).toBe('5.00e-4')
    expect(formatAmount(0)).toBe('0')
  })
})

describe('formatShare', () => {
  it('shows one decimal of a percentage', () => {
    expect(formatShare(0.5412)).toBe('54.1 %')
  })

  it('draws a dash where there is no share', () => {
    expect(formatShare(null)).toBe('–')
  })
})

describe('cutNotice', () => {
  it('says no share where the total is 0', () => {
    const notice = cutNotice({ cutoff: 0.01, below: 2, share: null, below_score: -0.02, unlisted: 1, unlisted_share: null, unlisted_score: 0.03 })
    expect(notice).toBe(
      '2 items under the 1.0 % cut-off are not shown, together no share of a total of 0. 1 item that reaches the 1.0 % cut-off is past the end of the list, together no share of a total of 0.',
    )
  })
})

describe('shortHash', () => {
  it('keeps the ends', () => {
    expect(shortHash('5b1c9e00000000000000000000000000000000000000000000000000000e2a1')).toBe('5b1c9e…e2a1')
    expect(shortHash(null)).toBe('')
  })
})

describe('categoryLabel', () => {
  const method: Method = { id: 'm_1', tuple: ['x', 'IPCC 2021', 'climate change: total', 'GWP20'], spec: 'x > IPCC 2021 > climate change: total > GWP20', unit: 'kg CO2-Eq', impact_method: 'IPCC 2021', impact_category: 'climate change: total', indicator: 'GWP20' }

  it('names the indicator beside the category, which alone is shared by several indicators', () => {
    expect(categoryLabel(method)).toBe('climate change: total · GWP20')
  })

  it('names a method whose indicator is its category once', () => {
    expect(categoryLabel({ ...method, indicator: 'climate change: total' })).toBe('climate change: total')
  })
})

describe('methodLabel', () => {
  const method: Method = { id: 'm_1', tuple: ['x', 'IPCC 2021', 'climate change: total', 'GWP20'], spec: 'x > IPCC 2021 > climate change: total > GWP20', unit: 'kg CO2-Eq', impact_method: 'IPCC 2021', impact_category: 'climate change: total', indicator: 'GWP20' }

  it('names the family above the category and the indicator', () => {
    expect(methodLabel(method)).toBe('IPCC 2021 › climate change: total · GWP20')
  })

  it('names a method whose indicator is its category once', () => {
    expect(methodLabel({ ...method, indicator: 'climate change: total' })).toBe('IPCC 2021 › climate change: total')
  })
})

describe('methodById', () => {
  const method: Method = { id: 'm_1', tuple: ['x', 'IPCC 2021', 'climate change: total', 'GWP20'], spec: 'x > IPCC 2021 > climate change: total > GWP20', unit: 'kg CO2-Eq', impact_method: 'IPCC 2021', impact_category: 'climate change: total', indicator: 'GWP20' }
  const other: Method = { ...method, id: 'm_2', indicator: 'GWP100' }

  it('answers the method an id names', () => {
    expect(methodById([method, other], 'm_2')).toBe(other)
  })

  it('throws for an id the answer does not list, naming it', () => {
    expect(() => methodById([method, other], 'm_3')).toThrow('m_3')
  })
})

describe('formatAgo', () => {
  const now = new Date('2026-09-20T12:00:00Z')

  it('says how long ago an instant was, in the largest whole unit', () => {
    expect(formatAgo('2026-09-20T11:59:40.899532Z', now)).toBe('just now')
    expect(formatAgo('2026-09-20T11:55:00Z', now)).toBe('5 min ago')
    expect(formatAgo('2026-09-20T09:00:00Z', now)).toBe('3 h ago')
    expect(formatAgo('2026-09-14T02:53:31.899532Z', now)).toBe('6 days ago')
    expect(formatAgo('2026-09-19T11:00:00Z', now)).toBe('1 day ago')
  })

  it('names the day once an instant is a month old', () => {
    expect(formatAgo('2026-07-01T08:00:00Z', now)).toBe('2026-07-01')
  })
})
