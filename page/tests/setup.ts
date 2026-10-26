import '@testing-library/jest-dom/vitest'

class ResizeObserverStub implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? ResizeObserverStub

class MediaQueryListStub extends EventTarget implements MediaQueryList {
  media: string
  matches: boolean
  onchange: ((this: MediaQueryList, ev: MediaQueryListEvent) => void) | null = null
  constructor(media: string) {
    super()
    this.media = media
    const width = /min-width:\s*(\d+)px/.exec(media)?.[1]
    this.matches = window.innerWidth >= Number(width ?? 0)
  }
  addListener(): void {}
  removeListener(): void {}
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
