import { splitBackgroundExchanges } from '@/editors/background/exchanges'
import { splitExchanges } from '@/editors/process/exchanges'
import { describeUncertainty } from '@/lib/uncertainty'
import system from './fixtures/system.json'
import backgroundProcess from './fixtures/background_process.json'
import type { BackgroundExchange, BackgroundProcess, ProductSystem } from '@/api/types'

const widget = (system.value as ProductSystem).processes.find((p) => p.code === 'widget')!
const background = (backgroundProcess.value as BackgroundProcess).exchanges! as BackgroundExchange[]

describe('splitExchanges', () => {
  it('puts product inputs and drawn flows under inputs, production and emitted flows under outputs', () => {
    const co2 = widget.exchanges.find((e) => e.type === 'elementary')!
    const split = splitExchanges(widget, { [co2.input!.kind === 'elementary_flow' ? co2.input!.id : '']: 'output' })
    expect(split.outputs[0].type).toBe('production')
    expect(split.outputs.map((e) => e.name)).toContain(co2.name)
    expect(split.inputs.every((e) => e.type === 'product')).toBe(true)
    expect(split.unresolved).toEqual([])
  })

  it('keeps a flow whose side is not yet answered apart', () => {
    const split = splitExchanges(widget, {})
    expect(split.unresolved.map((e) => e.type)).toEqual(['elementary'])
  })
})

describe('splitBackgroundExchanges', () => {
  const cutOff: BackgroundExchange = {
    amount: 0.25,
    cut_off: 'no provider for the input',
    flow: 'sand',
    input: null,
    reference: false,
    side: 'input',
    supplier: null,
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
  it('names the distribution and its parameters', () => {
    expect(describeUncertainty(null)).toBe('none')
    expect(describeUncertainty({ type: 'lognormal', params: { loc: -1.2, scale: 0.2 } })).toBe('lognormal · loc −1.2, scale 0.2')
    expect(describeUncertainty({ type: 'triangular', params: { minimum: 1.05, loc: 1.1, maximum: 1.2 } })).toBe('triangular · minimum 1.05, loc 1.1, maximum 1.2')
  })
})
