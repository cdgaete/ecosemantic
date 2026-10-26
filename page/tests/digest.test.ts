import { digestOf, holds } from '@/activity/digest'
import type { LogEntry } from '@/api/types'
import agentLog from './fixtures/agent_log.json'

const entries = agentLog.value as LogEntry[]

describe('digest', () => {
  it('counts the changes of an interval by operation and entity', () => {
    // #2 adds a process and its production exchange, #3 sets the reference, #4 adds an exchange, #5 edits an amount
    expect(digestOf(entries.filter((entry) => entry.seq > 1))).toEqual({ processes: 1, exchanges: 2, edits: 2, deletions: 0 })
  })

  it('names the entries a count counted', () => {
    expect(entries.filter((entry) => holds(entry, 'exchanges')).map((entry) => entry.seq)).toEqual([2, 4])
    expect(entries.filter((entry) => holds(entry, 'edits')).map((entry) => entry.seq)).toEqual([3, 5])
  })
})
