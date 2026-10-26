import { STREAM_KINDS } from './streamKinds'
import type { FromWorker, ToWorker } from './streamWorker'

type Listener = (event: MessageEvent) => void

export type EventStream = Pick<EventSource, 'readyState' | 'onopen' | 'onerror' | 'close'> & {
  addEventListener: (kind: string, listener: Listener) => void
}

class WorkerStream implements EventStream {
  readyState = 0
  onopen: EventSource['onopen'] = null
  onerror: EventSource['onerror'] = null
  private readonly listeners = new Map<string, Listener[]>()
  private readonly port: MessagePort
  private readonly url: string
  private readonly hidden = (): void => this.send({ type: 'close' })
  private readonly shown = (event: PageTransitionEvent): void => {
    if (event.persisted) this.send({ type: 'open', url: this.url })
  }

  constructor(url: string) {
    this.url = url
    this.port = new SharedWorker(new URL('./streamWorker.ts', import.meta.url), { type: 'module', name: 'ecosemantic-events' }).port
    this.port.onmessage = (e: MessageEvent) => this.receive(e.data as FromWorker)
    this.port.start()
    this.send({ type: 'open', url })
    window.addEventListener('pagehide', this.hidden)
    window.addEventListener('pageshow', this.shown)
  }

  private send(message: ToWorker): void {
    this.port.postMessage(message)
  }

  private receive(message: FromWorker): void {
    if (message.type === 'open') {
      this.readyState = 1
      this.onopen?.call(this as unknown as EventSource, new Event('open'))
    } else if (message.type === 'error') {
      if (message.closed) this.readyState = 2
      this.onerror?.call(this as unknown as EventSource, new Event('error'))
    } else if (STREAM_KINDS.includes(message.kind as (typeof STREAM_KINDS)[number])) {
      const event = new MessageEvent(message.kind, { data: message.data })
      this.listeners.get(message.kind)?.forEach((listener) => listener(event))
    }
  }

  addEventListener(kind: string, listener: Listener): void {
    this.listeners.set(kind, [...(this.listeners.get(kind) ?? []), listener])
  }

  close(): void {
    this.readyState = 2
    window.removeEventListener('pagehide', this.hidden)
    window.removeEventListener('pageshow', this.shown)
    this.send({ type: 'close' })
  }
}

let workerCapable: boolean | null = null

export function connectEvents(url: string): EventStream {
  workerCapable ??= typeof SharedWorker !== 'undefined'
  return workerCapable ? new WorkerStream(url) : new EventSource(url)
}
