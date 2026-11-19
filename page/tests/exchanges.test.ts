import { splitBackgroundExchanges } from '@/editors/explorer/exchanges'
import { describeUncertainty } from '@/lib/uncertainty'
import backgroundProcess from './fixtures/background_process.json'
import type { BackgroundExchange, BackgroundProcess } from '@/api/types'

const background = (backgroundProcess.value as BackgroundProcess).exchanges! as BackgroundExchange[]

describe('splitBackgroundExchanges', () => {
  const cutOff: BackgroundExchange = {
    amount: 0.25,
    cut_off: 'no provider for the input',
    flow: 'sand',
    input: null,
    reference: false,
    side: 'input',
    supplier: null,
    supplier_location: null,
    type: 'product',
    unit: 'kilogram',
  }

  it('puts every row under the side the source gives', () => {
    const split = splitBackgroundExchanges(background)
    expect(split.inputs.map((e) => e.flow)).toEqual(['electricity'])
    expect(split.outputs.map((e) => e.flow)).toEqual(['steel', 'Carbon dioxide, fossil', 'Methane, fossil'])
  })

  it('brings the reference row first and keeps the others in the position the catalog lists', () => {
    const split = splitBackgroundExchanges([...background].reverse())
    expect(split.outputs.map((e) => e.flow)).toEqual(['steel', 'Methane, fossil', 'Carbon dioxide, fossil'])
    expect(split.outputs[0].reference).toBe(true)
  })

  it('keeps a cut-off row in its section at its position', () => {
    const split = splitBackgroundExchanges([cutOff, ...background])
    expect(split.inputs.map((e) => e.flow)).toEqual(['sand', 'electricity'])
    expect(split.inputs[0].cut_off).toBe('no provider for the input')
  })
})

describe('describeUncertainty', () => {
  it('states each distribution the way a practitioner does, in the amount unit', () => {
    expect(describeUncertainty(null, 'km')).toBe('none')
    expect(describeUncertainty({ type: 'uniform', params: { minimum: 50, maximum: 300 } }, 'km')).toBe('uniform, 50 to 300 km')
    expect(describeUncertainty({ type: 'triangular', params: { minimum: 50, loc: 120, maximum: 300 } }, 'km')).toBe('triangular, 50 to 300 km, mode 120')
    expect(describeUncertainty({ type: 'normal', params: { loc: 100, scale: 2 } }, 'km')).toBe('normal, sd 2 km')
    expect(describeUncertainty({ type: 'lognormal', params: { loc: 0, scale: 0.1823 } }, '')).toBe('lognormal, GSD² 1.44')
  })

  it('adds the bound a lognormal or a normal states, both ends or one', () => {
    const bounded = { loc: 0, scale: 0.1823, minimum: 0.8, maximum: 1.6 }
    expect(describeUncertainty({ type: 'lognormal', params: bounded }, '')).toBe('lognormal, GSD² 1.44, bounded 0.8 to 1.6')
    expect(describeUncertainty({ type: 'lognormal', params: { loc: 0, scale: 0.1823, minimum: 0.8 } }, '')).toBe('lognormal, GSD² 1.44, at least 0.8')
    expect(describeUncertainty({ type: 'normal', params: { loc: 2, scale: 0.5, maximum: 4 } }, 'kg')).toBe('normal, sd 0.5 kg, at most 4 kg')
  })
})
