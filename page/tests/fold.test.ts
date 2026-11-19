import { folded, foldedLine } from '@/activity/fold'
import type { Call, CallOutcome, Effect } from '@/api/types'
import trail from './fixtures/trail.json'

const base = trail.value[0] as unknown as Call

function call(tool: string, effect: Effect, n: number, outcome: CallOutcome = 'ok'): Call {
  return { ...base, id: `${tool}-${n}`, tool, effect, outcome, summary: null, error: null }
}

const shape = (part: { kind: 'write'; call: Call } | { kind: 'reads'; calls: Call[] }): string =>
  part.kind === 'write' ? part.call.tool : `reads ${part.calls.length}`

describe('folded', () => {
  it('a write stands on its own and the reads between two writes fold into one part', () => {
    const calls = [call('create_exchange', 'write', 1), call('search_processes', 'read', 2), call('get_background_process', 'read', 3), call('update_exchange', 'write', 4)]
    const parts = folded(calls)
    expect(parts.map(shape)).toEqual(['create_exchange', 'reads 2', 'update_exchange'])
    expect(parts.map((part) => part.at)).toEqual([0, 1, 3])
  })

  it('a run of one read folds', () => {
    const parts = folded([call('create_exchange', 'write', 1), call('search_processes', 'read', 2), call('update_exchange', 'write', 3)])
    expect(parts.map(shape)).toEqual(['create_exchange', 'reads 1', 'update_exchange'])
    expect(parts[1].at).toBe(1)
  })

  it('the folded line counts each tool in the order it was first called', () => {
    const calls = [call('calculate_impact', 'compute', 1), call('list_requests', 'read', 2), call('calculate_impact', 'compute', 3), call('calculate_impact', 'compute', 4)]
    expect(foldedLine(calls)).toBe('calculate_impact ×3 · list_requests')
  })

  it('a failed read is counted in its folded line', () => {
    const calls = [call('search_processes', 'read', 1), call('search_processes', 'read', 2), call('search_processes', 'read', 3, 'error'), call('search_processes', 'read', 4)]
    expect(foldedLine(calls)).toBe('search_processes ×4, 1 failed')
    expect(foldedLine([call('search_processes', 'read', 5, 'error')])).toBe('search_processes, 1 failed')
  })

  it('a delete stands on its own', () => {
    const parts = folded([call('search_processes', 'read', 1), call('delete_exchange', 'delete', 2), call('search_methods', 'read', 3)])
    expect(parts.map(shape)).toEqual(['reads 1', 'delete_exchange', 'reads 1'])
    expect(parts.map((part) => part.at)).toEqual([0, 1, 2])
  })
})
