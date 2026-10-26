import { hub } from '@/api/streamWorker'

type Listener = (e: MessageEvent) => void

class FakePort {
  other: FakePort | null = null
  onmessage: Listener | null = null
  postMessage(data: unknown): void {
    const target = this.other
    target?.onmessage?.(new MessageEvent('message', { data }))
  }
  start(): void {}
  close(): void {}
}

function pair(): [FakePort, FakePort] {
  const a = new FakePort()
  const b = new FakePort()
  a.other = b
  b.other = a
  return [a, b]
}

export class FakeSharedWorker {
  static connect: ((port: MessagePort) => void) | null = null
  port: MessagePort
  constructor() {
    FakeSharedWorker.connect ??= hub((url) => new EventSource(url))
    const [tab, worker] = pair()
    this.port = tab as unknown as MessagePort
    FakeSharedWorker.connect(worker as unknown as MessagePort)
  }
}
