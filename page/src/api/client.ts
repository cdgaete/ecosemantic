import type {
  AgentSummary,
  Answer,
  BackgroundProcess,
  Call,
  ContributionArguments,
  ContributionResult,
  Credential,
  CredentialKind,
  Database,
  DatabaseSource,
  ElementaryFlow,
  ElementaryFlowHit,
  ErrorEnvelope,
  ImpactArguments,
  ImpactResult,
  InventoryArguments,
  InventoryListing,
  Install,
  InstallDraft,
  Listing,
  LogEntry,
  ParameterSpace,
  Arrangement,
  Method,
  ProcessHit,
  ProductSystem,
  Request,
  RequestDraft,
  Rerun,
  Run,
  ServerInfo,
  StartRunArguments,
  SystemCard,
  SystemRead,
  Term,
  ValidationReport,
  Value,
  VocabularyKind,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly kind: string
  readonly details: ErrorEnvelope['details']
  constructor(status: number, envelope: ErrorEnvelope) {
    super(envelope.message)
    this.status = status
    this.kind = envelope.error
    this.details = envelope.details
  }
}

let token: string | null = null

export function rememberToken(fromSearch: string): void {
  const found = new URLSearchParams(fromSearch).get('token')
  if (found) token = found
}

export function currentToken(): string | null {
  return token
}

export function withToken(path: string): string {
  if (!token) return path
  const [base, search = ''] = path.split('?')
  const params = new URLSearchParams(search)
  params.set('token', token)
  return `${base}?${params.toString()}`
}

export function withoutToken(path: string): string {
  const [base, search] = path.split('?')
  if (search === undefined) return path
  const params = new URLSearchParams(search)
  params.delete('token')
  const rest = params.toString()
  return rest ? `${base}?${rest}` : base
}

const inflight = new Map<number, number>()
let calls = 0

export function oldestPending(now: number = Date.now()): number | null {
  if (inflight.size === 0) return null
  return now - Math.min(...inflight.values())
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const id = calls++
  inflight.set(id, Date.now())
  try {
    const response = await fetch(withToken(path), { ...init, headers: { 'content-type': 'application/json', ...init?.headers } })
    const text = await response.text()
    const body: unknown = text ? JSON.parse(text) : null
    if (!response.ok) {
      const envelope = body as ErrorEnvelope
      throw new ApiError(response.status, envelope)
    }
    return body as T
  } finally {
    inflight.delete(id)
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

const systems = '/api/product-systems'
const databases = '/api/databases'

async function postForm(path: string, field: string, file: File, actor: string, stated: Record<string, string> = {}): Promise<LogEntry> {
  const form = new FormData()
  form.set(field, file)
  form.set('actor', actor)
  for (const [name, value] of Object.entries(stated)) form.set(name, value)
  const response = await fetch(withToken(path), { method: 'POST', body: form })
  const body: unknown = await response.json()
  if (!response.ok) throw new ApiError(response.status, body as ErrorEnvelope)
  return body as LogEntry
}

export const api = {
  databases: () => call<Answer<Database[]>>(databases),
  vocabulary: (database: string, kind: VocabularyKind) => call<Answer<Term[]>>(`${databases}/${database}/vocabulary/${kind}`),
  searchProcesses: (database: string, params: { query: string; location?: string; unit?: string; limit?: number; cursor?: string }) =>
    call<Listing<ProcessHit>>(`${databases}/${database}/processes${query(params)}`),
  searchElementaryFlows: (database: string, params: { query: string; compartment?: string; limit?: number; cursor?: string }) =>
    call<Listing<ElementaryFlowHit>>(`${databases}/${database}/elementary-flows${query(params)}`),
  searchMethods: (database: string, params: { query: string; limit?: number; cursor?: string }) =>
    call<Listing<Method>>(`${databases}/${database}/methods${query(params)}`),
  backgroundProcess: (database: string, ref: string) => call<Answer<BackgroundProcess>>(`${databases}/${database}/processes/${ref}`),
  elementaryFlow: (database: string, id: string) => call<Answer<ElementaryFlow>>(`${databases}/${database}/elementary-flows/${id}`),
  systems: (signal?: AbortSignal) => call<Answer<SystemCard[]>>(systems, { signal }),
  system: (id: string, signal?: AbortSignal) => call<SystemRead>(`${systems}/${id}`, { signal }),
  systemAs: (id: string, variant: string) => call<SystemRead>(`${systems}/${id}?variant=${encodeURIComponent(variant)}`),
  parameters: (id: string, hash?: string) => call<Answer<ParameterSpace>>(`${systems}/${id}/parameters${query({ hash })}`),
  log: (id: string, signal?: AbortSignal) => call<Answer<LogEntry[]>>(`${systems}/${id}/log`, { signal }),
  version: (id: string, hash: string) => call<ProductSystem>(`${systems}/${id}/versions/${hash}`),
  validation: (id: string, target?: string, signal?: AbortSignal) => call<Answer<ValidationReport>>(`${systems}/${id}/validation${query({ target })}`, { signal }),
  anchors: (id: string, signal?: AbortSignal) => call<Answer<string[]>>(`${systems}/${id}/anchors`, { signal }),
  layout: (id: string, variant: string | null = null, signal?: AbortSignal) =>
    call<Answer<Arrangement>>(`${systems}/${id}/layout${query({ variant: variant ?? undefined })}`, { signal }),
  placeCards: (id: string, placements: { code: string; x: number; y: number }[], variant: string | null = null) =>
    call<Answer<Arrangement>>(`${systems}/${id}/layout`, { method: 'POST', body: JSON.stringify(variant === null ? { placements } : { placements, variant }) }),
  releaseCards: (id: string, variant: string | null = null) => call<Answer<Arrangement>>(`${systems}/${id}/layout${query({ variant: variant ?? undefined })}`, { method: 'DELETE' }),
  agents: (signal?: AbortSignal) => call<Value<AgentSummary[]>>('/api/agents', { signal }),
  activity: (params: { agent?: string; product_system_id?: string; after?: string }) => call<Value<Call[]>>(`/api/activity${query(params)}`),
  trail: (id: string, seq: number) => call<Value<Call[]>>(`${systems}/${id}/log/${seq}/trail`),
  openTrail: (agent: string, systemId: string, signal?: AbortSignal) =>
    call<Value<Call[]>>(`/api/agents/${encodeURIComponent(agent)}/trail?product_system_id=${encodeURIComponent(systemId)}`, { signal }),
  rerun: (callId: string) => call<Value<Rerun>>(`/api/activity/${callId}/rerun`, { method: 'POST' }),
  allEventsUrl: () => withToken('/api/events'),
  impact: (id: string, body: ImpactArguments, started = false) =>
    call<Answer<ImpactResult>>(`${systems}/${id}/impact${started ? '?started=true' : ''}`, { method: 'POST', body: JSON.stringify(body) }),
  calculations: (id: string) => call<Value<Call[]>>(`${systems}/${id}/calculations`),
  contributions: (id: string, body: ContributionArguments) =>
    call<Answer<ContributionResult>>(`${systems}/${id}/contributions`, { method: 'POST', body: JSON.stringify(body) }),
  inventory: (id: string, body: InventoryArguments) => call<InventoryListing>(`${systems}/${id}/inventory`, { method: 'POST', body: JSON.stringify(body) }),
  runs: (id: string) => call<Answer<Run[]>>(`${systems}/${id}/runs`),
  startRun: (id: string, body: StartRunArguments) => call<Answer<Run>>(`${systems}/${id}/runs?started=true`, { method: 'POST', body: JSON.stringify(body) }),
  run: (runId: string) => call<Answer<Run>>(`/api/runs/${runId}`),
  cancelRun: (runId: string) => call<Answer<Run>>(`/api/runs/${runId}/cancel`, { method: 'POST' }),
  sources: () => call<Answer<DatabaseSource[]>>('/api/sources'),
  installs: () => call<Answer<Install[]>>('/api/installs'),
  install: (id: string) => call<Answer<Install>>(`/api/installs/${id}`),
  postInstall: (body: Omit<InstallDraft, 'actor'>) => call<Answer<Install>>('/api/installs', { method: 'POST', body: JSON.stringify(body) }),
  cancelInstall: (id: string) => call<Answer<Install>>(`/api/installs/${id}/cancel`, { method: 'POST' }),
  uploadDatabase: async (form: FormData): Promise<Answer<Install>> => {
    const response = await fetch(withToken('/api/installs/openlca'), { method: 'POST', body: form })
    const body: unknown = await response.json()
    if (!response.ok) throw new ApiError(response.status, body as ErrorEnvelope)
    return body as Answer<Install>
  },
  licenceUrl: (id: string) => withToken(`/api/installs/${id}/licence`),
  credentials: () => call<{ held: CredentialKind[] }>('/api/credentials'),
  putCredential: (kind: CredentialKind, account: Credential) => call<null>(`/api/credentials/${kind}`, { method: 'PUT', body: JSON.stringify(account) }),
  deleteCredential: (kind: CredentialKind) => call<null>(`/api/credentials/${kind}`, { method: 'DELETE' }),
  server: () => call<ServerInfo>('/api/server'),
  requests: (id: string) => call<Answer<Request[]>>(`${systems}/${id}/requests`),
  postRequest: (id: string, draft: RequestDraft) => call<Request>(`${systems}/${id}/requests`, { method: 'POST', body: JSON.stringify(draft) }),
  packageUrl: (id: string) => withToken(`${systems}/${id}/package.zip`),
  tablesUrl: (id: string) => withToken(`${systems}/${id}/tables.zip`),
  eventsUrl: (id: string) => withToken(`${systems}/${id}/events`),
  returnPackage: (id: string, file: File, actor: string, atEntry: string) =>
    postForm(`${systems}/${id}/return`, 'package', file, actor, atEntry ? { at_entry: atEntry } : {}),
  returnTables: (id: string, file: File, actor: string) => postForm(`${systems}/${id}/tables`, 'tables', file, actor),
  resultZip: async (id: string, kind: 'impact' | 'contributions' | 'inventory', body: object): Promise<Blob> => {
    const response = await fetch(withToken(`${systems}/${id}/${kind}.zip`), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
    if (!response.ok) throw new ApiError(response.status, (await response.json()) as ErrorEnvelope)
    return response.blob()
  },
}
