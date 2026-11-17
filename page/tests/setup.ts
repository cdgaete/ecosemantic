import '@testing-library/jest-dom/vitest'

class ResizeObserverStub implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? ResizeObserverStub

const LIVE_QUERIES = new Set<MediaQueryListStub>()

class MediaQueryListStub extends EventTarget implements MediaQueryList {
  media: string
  matches: boolean
  onchange: ((this: MediaQueryList, ev: MediaQueryListEvent) => void) | null = null
  private readonly minimum: number
  constructor(media: string) {
    super()
    this.media = media
    this.minimum = Number(/min-width:\s*(\d+)px/.exec(media)?.[1] ?? 0)
    this.matches = window.innerWidth >= this.minimum
    LIVE_QUERIES.add(this)
  }
  addListener(): void {}
  removeListener(): void {}
  settle(): void {
    const matches = window.innerWidth >= this.minimum
    if (matches === this.matches) return
    this.matches = matches
    this.dispatchEvent(new Event('change'))
  }
}

export function resizePage(width: number): void {
  window.innerWidth = width
  for (const query of LIVE_QUERIES) query.settle()
}

globalThis.matchMedia = globalThis.matchMedia ?? ((query: string) => new MediaQueryListStub(query))

class EventSourceStub implements EventSource {
  static readonly CONNECTING = 0 as const
  static readonly OPEN = 1 as const
  static readonly CLOSED = 2 as const
  readonly CONNECTING = 0 as const
  readonly OPEN = 1 as const
  readonly CLOSED = 2 as const
  readonly url: string
  readonly withCredentials = false
  readyState = 0
  onopen: ((this: EventSource, ev: Event) => unknown) | null = null
  onmessage: ((this: EventSource, ev: MessageEvent) => unknown) | null = null
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null
  constructor(url: string | URL) {
    this.url = url.toString()
  }
  close(): void {
    this.readyState = 2
  }
  addEventListener(): void {}
  removeEventListener(): void {}
  dispatchEvent(): boolean {
    return true
  }
}
globalThis.EventSource = globalThis.EventSource ?? EventSourceStub

Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? ((): void => undefined)
