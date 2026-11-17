import { digestOf, digestPhrases, holds } from '@/activity/digest'
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

  it('phrases every count of a digest in the order of its kinds, a zero and a one included', () => {
    expect(digestPhrases({ processes: 2, exchanges: 0, edits: 1, deletions: 3 })).toEqual([
      { key: 'processes', text: '2 processes added' },
      { key: 'exchanges', text: '0 exchanges added' },
      { key: 'edits', text: '1 value edited' },
      { key: 'deletions', text: '3 deletions' },
    ])
  })
})
