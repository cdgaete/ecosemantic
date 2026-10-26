import { connectEvents } from '@/api/connect'
import { FakeSource } from './fakeSource'

it('opens its own stream where SharedWorker is undefined', () => {
  FakeSource.instances = []
  vi.stubGlobal('EventSource', FakeSource)
  const source = connectEvents('/api/events')
  expect(FakeSource.instances).toHaveLength(1)
  expect(source).toBe(FakeSource.instances[0])
  vi.unstubAllGlobals()
})
