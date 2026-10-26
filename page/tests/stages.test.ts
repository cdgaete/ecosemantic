import { groupByStage, stageOrder } from '@/lib/stages'
import system from './fixtures/system.json'
import type { Process, ProductSystem } from '@/api/types'

const doc = system.value as ProductSystem

function withStages(stages: Record<string, string | null>): ProductSystem {
  return {
    ...doc,
    processes: doc.processes.map((p: Process) => ({ ...p, metadata: { ...p.metadata, life_cycle_stage: stages[p.code] ?? null } })),
  }
}

describe('stages', () => {
  it('orders stages by first appearance walking from the anchors', () => {
    const staged = withStages({ widget: 'use', frame: 'manufacturing' })
    expect(stageOrder(staged, ['widget'])).toEqual(['use', 'manufacturing'])
    expect(stageOrder(staged, ['frame'])).toEqual(['manufacturing', 'use'])
  })

  it('orders stages by declaration when no anchor is named', () => {
    const staged = withStages({ widget: 'use', frame: 'manufacturing' })
    const byCode = (code: string) => staged.processes.find((p) => p.code === code)!
    expect(stageOrder({ ...staged, processes: [byCode('frame'), byCode('widget')] }, [])).toEqual(['manufacturing', 'use'])
    expect(stageOrder({ ...staged, processes: [byCode('widget'), byCode('frame')] }, [])).toEqual(['use', 'manufacturing'])
  })

  it('groups processes under their stage, unstaged last', () => {
    const staged = withStages({ widget: 'use', frame: null })
    const groups = groupByStage(staged, ['widget'])
    expect(groups.map((g) => g.stage)).toEqual(['use', 'no stage'])
    expect(groups[0].processes.map((p) => p.code)).toEqual(['widget'])
    expect(groups[1].processes.map((p) => p.code)).toEqual(['frame'])
  })
})
