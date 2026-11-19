import { colourOf, colourOfEntry, quietSince } from '@/activity/agents'
import type { LogEntry } from '@/api/types'
import agentLog from './fixtures/agent_log.json'
import log from './fixtures/log.json'

describe('agents', () => {
  it('gives an agent one colour of the palette, always the same', () => {
    expect(colourOf('electricity')).toBe(colourOf('electricity'))
    expect(colourOf('electricity')).toMatch(/^rgb\(var\(--chart-[1-7]\)\)$/)
  })

  it("colours an entry by its agent, and a person's entry by the highlight", () => {
    expect(colourOfEntry(agentLog.value[0] as LogEntry)).toBe(colourOf('fixture-agent'))
    expect(colourOfEntry({ ...(log.value[0] as LogEntry), actor: { kind: 'person', id: null, name: 'Carlos' } })).toBe('rgb(var(--highlight))')
  })

  it('a trail is quiet two minutes after its last call', () => {
    const now = Date.parse('2026-11-19T16:00:00Z')
    const before = (seconds: number) => new Date(now - seconds * 1_000).toISOString()
    expect(quietSince(before(119), now)).toBe(false)
    expect(quietSince(before(121), now)).toBe(true)
  })
})
