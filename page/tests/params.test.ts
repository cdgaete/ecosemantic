import { parseParams, serializeParams, toImpactArguments } from '@/editors/results/params'

describe('result params', () => {
  it('round-trips through the query string and reads no Monte Carlo block', () => {
    const params = { impact_method: 'IPCC 2021', variants: ['small', 'organic'], amount: 2 }
    const search = serializeParams(params)
    expect(parseParams(search)).toEqual(params)
    expect(parseParams('?impact_method=IPCC&mc=100,1000,0.05,42')).toEqual({ impact_method: 'IPCC', variants: [], amount: 1 })
    expect(parseParams('?method_id=m_0123456789')).toEqual({ method_id: 'm_0123456789', variants: [], amount: 1 })
    expect(parseParams('?')).toBeNull()
  })

  it('builds the tool arguments, with a demand only when the amount is not one', () => {
    expect(toImpactArguments({ method_id: 'm_1', variants: [], amount: 1 }, 'widget')).toEqual({ method_id: 'm_1', variants: [] })
    expect(toImpactArguments({ impact_method: 'IPCC', variants: ['small'], amount: 3 }, 'widget')).toEqual({
      impact_method: 'IPCC',
      variants: ['small'],
      demand: [{ ref: { kind: 'foreground', code: 'widget' }, amount: 3 }],
    })
  })

  it('hands a demand on as it was recorded', () => {
    const demand = [{ ref: { kind: 'foreground' as const, code: 'frame' }, amount: 2 }]
    expect(toImpactArguments({ method_id: 'm_1', variants: ['heavy'], amount: 1, demand }, 'widget')).toEqual({ method_id: 'm_1', variants: ['heavy'], demand })
  })
})
