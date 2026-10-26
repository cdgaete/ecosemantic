export class FakeSource {
  static readonly CLOSED = 2
  static instances: FakeSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 0
  constructor(url: string) {
    this.url = url
    FakeSource.instances.push(this)
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  emit(type: string, data: unknown) {
    this.listeners[type]?.forEach((fn) => fn(new MessageEvent(type, { data: JSON.stringify(data) })))
  }
  close() {
    this.readyState = 2
  }
}
