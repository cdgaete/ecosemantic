import { STREAM_KINDS } from './streamKinds'

export type ToWorker = { type: 'open'; url: string } | { type: 'close' }
export type FromWorker = { type: 'event'; kind: string; data: string } | { type: 'open' } | { type: 'error'; closed: boolean }

const OPEN = 1
const CLOSED = 2

interface Stream {
  source: EventSource
  ports: Set<MessagePort>
}

export function hub(open: (url: string) => EventSource): (port: MessagePort) => void {
  const streams = new Map<string, Stream>()
  const tell = (url: string, message: FromWorker) => streams.get(url)?.ports.forEach((port) => port.postMessage(message))
  const opened = (url: string): EventSource => {
    const source = open(url)
    source.onopen = () => tell(url, { type: 'open' })
    source.onerror = () => tell(url, { type: 'error', closed: source.readyState === CLOSED })
    for (const kind of STREAM_KINDS) source.addEventListener(kind, (e) => tell(url, { type: 'event', kind, data: (e as MessageEvent).data as string }))
    return source
  }
  const attach = (url: string, port: MessagePort): void => {
    const held = streams.get(url)
    const stream = held !== undefined && held.source.readyState !== CLOSED ? held : { source: opened(url), ports: held?.ports ?? new Set<MessagePort>() }
    streams.set(url, stream)
    stream.ports.add(port)
    if (stream.source.readyState === OPEN) port.postMessage({ type: 'open' } satisfies FromWorker)
  }
  const detach = (url: string, port: MessagePort): void => {
    const stream = streams.get(url)
    if (stream === undefined) return
    stream.ports.delete(port)
    if (stream.ports.size > 0) return
    stream.source.close()
    streams.delete(url)
  }
  return (port) => {
    let joined: string | null = null
    port.onmessage = (e: MessageEvent) => {
      const message = e.data as ToWorker
      if (message.type === 'open') {
        joined = message.url
        attach(message.url, port)
      } else if (joined !== null) {
        detach(joined, port)
        joined = null
      }
    }
    port.start()
  }
}

interface ConnectScope {
  onconnect: ((e: MessageEvent) => void) | null
}

declare const self: unknown

if (typeof self === 'object' && self !== null && 'onconnect' in self && typeof window === 'undefined') {
  const connect = hub((url) => new EventSource(url))
  ;(self as ConnectScope).onconnect = (e: MessageEvent) => connect(e.ports[0])
}
