import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { create } from 'zustand'
import { useUi } from '@/store/ui'
import { api, oldestPending } from './client'
import { connectEvents, type EventStream } from './connect'
import { keys } from './queries'
import { STREAM_KINDS } from './streamKinds'
import type { LogEntry, StreamEvent, SystemRead } from './types'

export type Connection = 'connecting' | 'open' | 'retrying' | 'closed'
const MAX_ERRORS = 30
const OPEN = 1
const CLOSED = 2

interface LiveStore {
  connection: Connection
  blocked: boolean
  streams: number
  latest: Record<string, LogEntry>
  errors: number
  set: (patch: Partial<LiveStore>) => void
}

export const useLive = create<LiveStore>()((set) => ({
  connection: 'closed',
  blocked: false,
  streams: 0,
  latest: {},
  errors: 0,
  set: (patch) => set(patch),
}))

type GoRef = { current: (path: string) => void }

interface Followed {
  refCount: number
  goRefs: Set<GoRef>
}

interface Shared {
  source: EventStream
  client: QueryClient
  processes: number
}

const followed = new Map<string, Followed>()
let shared: Shared | null = null

export const WAIT_DEADLINE = 3000

export function openStreams(): number {
  return shared === null ? 0 : 1
}

export function watchWaiting(): void {
  const pending = oldestPending()
  const streams = openStreams()
  useLive.getState().set({ streams, blocked: streams > 0 && pending !== null && pending > WAIT_DEADLINE })
}

function invalidate(client: QueryClient, ...queryKeys: (readonly unknown[])[]): void {
  queryKeys.forEach((queryKey) => void client.invalidateQueries({ queryKey }))
}

function withoutLatest(systemId: string): Record<string, LogEntry> {
  return Object.fromEntries(Object.entries(useLive.getState().latest).filter(([id]) => id !== systemId))
}

function forSystem(systemId: string, client: QueryClient, event: StreamEvent): void {
  if (event.kind === 'entry') {
    const entry = event.entry
    if (entry) useLive.getState().set({ latest: { ...useLive.getState().latest, [systemId]: entry } })
    invalidate(client, keys.system(systemId), keys.log(systemId), keys.validation(systemId), keys.anchors(systemId), keys.layouts(systemId), ['parameters', systemId])
  } else if (event.kind === 'layout') invalidate(client, keys.layouts(systemId))
  else if (event.kind === 'request' || event.kind === 'resolution') invalidate(client, keys.requests(systemId), keys.system(systemId))
  else if (event.kind === 'run') {
    if (event.run) client.setQueryData(keys.run(event.run.id), { value: event.run, hint: null, view_url: null })
    invalidate(client, keys.runs(systemId))
  } else if (event.kind === 'deleted') {
    const gone = followed.get(systemId)
    followed.delete(systemId)
    useUi.getState().unpinWhere((tab) => tab.path.startsWith(`/systems/${systemId}`))
    if (useUi.getState().canvasSystemId === systemId) useUi.getState().setCanvasSystem(null)
    useLive.getState().set({ latest: withoutLatest(systemId) })
    gone?.goRefs.forEach((ref) => ref.current('/'))
  }
}

function links(client: QueryClient, systemId: string, linked: string): boolean {
  const read = client.getQueryData<SystemRead>(keys.system(systemId))
  return read !== undefined && read.value.processes.some((p) => p.exchanges.some((e) => e.input?.kind === 'system' && e.input.product_system_id === linked))
}

function forLinking(client: QueryClient, event: StreamEvent): void {
  if (event.kind !== 'entry' || event.product_system_id === null) return
  for (const systemId of followed.keys()) if (systemId !== event.product_system_id && links(client, systemId, event.product_system_id)) invalidate(client, keys.validation(systemId))
}

function forProcess(client: QueryClient, event: StreamEvent): void {
  if (event.kind === 'call') {
    invalidate(client, keys.agents, ['calls'], ['calculations'])
    if (event.call) invalidate(client, keys.openTrail(event.call.agent))
  } else if (event.kind === 'install') {
    invalidate(client, keys.installs)
    if (event.install?.status === 'done') invalidate(client, keys.databases)
  } else if (event.kind === 'entry' || event.kind === 'deleted') invalidate(client, keys.systems)
}

function openShared(client: QueryClient): EventStream {
  const source = connectEvents(api.allEventsUrl())
  useLive.getState().set({ connection: source.readyState === OPEN ? 'open' : 'connecting', errors: 0 })
  source.onopen = () => useLive.getState().set({ connection: 'open', errors: 0 })
  source.onerror = () => {
    if (source.readyState === CLOSED) {
      useLive.getState().set({ connection: 'closed' })
      return
    }
    const errors = useLive.getState().errors + 1
    if (errors > MAX_ERRORS) {
      source.close()
      useLive.getState().set({ connection: 'closed', errors })
    } else useLive.getState().set({ connection: 'retrying', errors })
  }
  for (const kind of STREAM_KINDS)
    source.addEventListener(kind, (e) => {
      const event = JSON.parse(e.data as string) as StreamEvent
      if (shared?.processes) forProcess(client, event)
      if (event.product_system_id !== null && followed.has(event.product_system_id)) forSystem(event.product_system_id, client, event)
      forLinking(client, event)
    })
  return source
}

function share(client: QueryClient): Shared {
  if (shared === null) shared = { source: openShared(client), client, processes: 0 }
  return shared
}

function unshare(): void {
  if (shared === null || shared.processes > 0 || followed.size > 0) return
  shared.source.close()
  shared = null
  useLive.getState().set({ connection: 'closed' })
}

function follow(systemId: string, client: QueryClient, goRef: GoRef): void {
  share(client)
  const existing = followed.get(systemId)
  if (existing) {
    existing.refCount += 1
    existing.goRefs.add(goRef)
  } else followed.set(systemId, { refCount: 1, goRefs: new Set([goRef]) })
}

function unfollow(systemId: string, goRef: GoRef): void {
  const existing = followed.get(systemId)
  if (existing) {
    existing.goRefs.delete(goRef)
    existing.refCount -= 1
    if (existing.refCount === 0) followed.delete(systemId)
  }
  unshare()
}

export function reconnect(): void {
  if (shared === null) return
  shared.source.close()
  shared.source = openShared(shared.client)
}

export function followProcess(client: QueryClient): () => void {
  share(client).processes += 1
  return () => {
    if (shared !== null) shared.processes -= 1
    unshare()
  }
}

export function useHeldStream(): void {
  const client = useQueryClient()
  useEffect(() => followProcess(client), [client])
}

const noGo = (): void => undefined

export function useSystemStream(systemId: string, go: (path: string) => void = noGo): void {
  const client = useQueryClient()
  const goRef = useRef(go)
  useEffect(() => {
    goRef.current = go
  })
  useEffect(() => {
    follow(systemId, client, goRef)
    return () => unfollow(systemId, goRef)
  }, [client, systemId])
}
