import { folded } from '@/activity/fold'
import type { Call } from '@/api/types'
import trail from './fixtures/trail.json'

const base = trail.value[0] as unknown as Call
const quiet = (tool: string, n: number): Call => ({ ...base, id: `${tool}-${n}`, tool, outcome: 'ok', summary: null, error: null })
const searched = (n: number): Call => ({
  ...base,
  id: `search-${n}`,
  tool: 'search_processes',
  summary: { count: 2, more: false, items: [{ label: 'hit', detail: null, kind: 'background', database: 'db', ref: 'r' }], scores: [] },
})

describe('folded', () => {
  it('folds three or more consecutive quiet calls of one tool into one run', () => {
    const parts = folded([quiet('arrange_graph', 1), quiet('arrange_graph', 2), quiet('arrange_graph', 3)])
    expect(parts).toEqual([{ kind: 'run', tool: 'arrange_graph', calls: expect.any(Array), at: 0 }])
  })

  it('leaves two alone', () => {
    expect(folded([quiet('graph_layout', 1), quiet('graph_layout', 2)]).map((p) => p.kind)).toEqual(['call', 'call'])
  })

  it('keeps a call with candidates, or a failed one, out of any run, and counts positions in the trail', () => {
    const calls = [quiet('arrange_graph', 1), quiet('arrange_graph', 2), quiet('arrange_graph', 3), searched(1), { ...quiet('arrange_graph', 4), outcome: 'error' as const }, quiet('arrange_graph', 5)]
    const parts = folded(calls)
    expect(parts.map((p) => (p.kind === 'run' ? `run@${p.at}` : `call@${p.at}`))).toEqual(['run@0', 'call@3', 'call@4', 'call@5'])
  })

  it('leaves another tool between two runs out of them', () => {
    const calls = [quiet('arrange_graph', 1), quiet('arrange_graph', 2), quiet('arrange_graph', 3), quiet('graph_layout', 4), quiet('arrange_graph', 5), quiet('arrange_graph', 6), quiet('arrange_graph', 7)]
    const parts = folded(calls)
    expect(parts.map((p) => (p.kind === 'run' ? `${p.tool}@${p.at}` : `call@${p.at}`))).toEqual(['arrange_graph@0', 'call@3', 'arrange_graph@4'])
  })
})
