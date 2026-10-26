import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { ContributionArguments, Credential, CredentialKind, ImpactArguments, InstallDraft, InventoryArguments, RequestDraft, StartRunArguments, VocabularyKind } from './types'

export const keys = {
  databases: ['databases'] as const,
  vocabulary: (database: string, kind: VocabularyKind) => ['vocabulary', database, kind] as const,
  systems: ['systems'] as const,
  system: (id: string) => ['system', id] as const,
  log: (id: string) => ['log', id] as const,
  parameters: (id: string, hash: string | null) => ['parameters', id, hash] as const,
  validation: (id: string) => ['validation', id] as const,
  anchors: (id: string) => ['anchors', id] as const,
  layouts: (id: string) => ['layout', id] as const,
  layout: (id: string, variant: string | null) => ['layout', id, variant] as const,
  agents: ['agents'] as const,
  calls: (id: string, after: string | null) => ['calls', id, after] as const,
  trail: (id: string, seq: number) => ['trail', id, seq] as const,
  openTrail: (agent: string) => ['open-trail', agent] as const,
  requests: (id: string) => ['requests', id] as const,
  version: (id: string, hash: string) => ['version', id, hash] as const,
  background: (database: string, ref: string) => ['background', database, ref] as const,
  flow: (database: string, id: string) => ['flow', database, id] as const,
  search: (database: string, kind: string, params: Record<string, string | number | undefined>) => ['search', database, kind, params] as const,
  impacts: (id: string) => ['impact', id] as const,
  impact: (id: string, hash: string, body: ImpactArguments) => ['impact', id, hash, body] as const,
  calculations: (id: string) => ['calculations', id] as const,
  contributions: (id: string, hash: string, body: ContributionArguments) => ['contributions', id, hash, body] as const,
  inventory: (id: string, hash: string, body: InventoryArguments) => ['inventory', id, hash, body] as const,
  runs: (id: string) => ['runs', id] as const,
  run: (runId: string) => ['run', runId] as const,
  sources: ['sources'] as const,
  installs: ['installs'] as const,
  credentials: ['credentials'] as const,
  server: ['server'] as const,
}

export const forever = { staleTime: Infinity, gcTime: 30 * 60 * 1000 }

export const useDatabases = () => useQuery({ queryKey: keys.databases, queryFn: api.databases, ...forever })
export const useVocabulary = (database: string, kind: VocabularyKind) =>
  useQuery({ queryKey: keys.vocabulary(database, kind), queryFn: () => api.vocabulary(database, kind), ...forever })
export const useSystems = () => useQuery({ queryKey: keys.systems, queryFn: ({ signal }) => api.systems(signal), ...forever })
export const useSystem = (id: string, enabled = true) => useQuery({ queryKey: keys.system(id), queryFn: ({ signal }) => api.system(id, signal), enabled, ...forever })
export const useSystemAs = (id: string, variant: string | null) =>
  useQuery({ queryKey: [...keys.system(id), 'variant', variant] as const, queryFn: () => api.systemAs(id, variant!), enabled: variant !== null, ...forever })
export const useLog = (id: string) => useQuery({ queryKey: keys.log(id), queryFn: ({ signal }) => api.log(id, signal), ...forever })
export const useParameters = (id: string, hash: string | null) =>
  useQuery({ queryKey: keys.parameters(id, hash), queryFn: () => api.parameters(id, hash ?? undefined), ...forever })
export const useValidation = (id: string, enabled = true) => useQuery({ queryKey: keys.validation(id), queryFn: ({ signal }) => api.validation(id, undefined, signal), enabled, ...forever })
export const useAnchors = (id: string, enabled = true) => useQuery({ queryKey: keys.anchors(id), queryFn: ({ signal }) => api.anchors(id, signal), enabled, ...forever })
export const useAgents = () => useQuery({ queryKey: keys.agents, queryFn: ({ signal }) => api.agents(signal), ...forever })
export const useCalls = (id: string, after: string | null, enabled = true) =>
  useQuery({ queryKey: keys.calls(id, after), queryFn: () => api.activity({ product_system_id: id, after: after ?? undefined }), enabled, ...forever })
export const useTrail = (id: string, seq: number, enabled = true) => useQuery({ queryKey: keys.trail(id, seq), queryFn: () => api.trail(id, seq), enabled, ...forever })
export const useOpenTrail = (agent: string, systemId: string) =>
  useQuery({ queryKey: [...keys.openTrail(agent), systemId], queryFn: ({ signal }) => api.openTrail(agent, systemId, signal), ...forever })
export const useRerun = () => useMutation({ mutationFn: (callId: string) => api.rerun(callId) })
export const useRequests = (id: string) => useQuery({ queryKey: keys.requests(id), queryFn: () => api.requests(id), ...forever })
export const useVersion = (id: string, hash: string) => useQuery({ queryKey: keys.version(id, hash), queryFn: () => api.version(id, hash), ...forever })
export const useBackgroundProcess = (database: string, ref: string) =>
  useQuery({ queryKey: keys.background(database, ref), queryFn: () => api.backgroundProcess(database, ref), ...forever })
export const useElementaryFlow = (database: string, id: string) =>
  useQuery({ queryKey: keys.flow(database, id), queryFn: () => api.elementaryFlow(database, id), ...forever })
export const useSearchProcesses = (database: string, params: { query: string; location?: string; unit?: string; limit?: number; cursor?: string }) =>
  useQuery({ queryKey: keys.search(database, 'processes', params), queryFn: () => api.searchProcesses(database, params), enabled: params.query.length > 0, ...forever })
export const useSearchElementaryFlows = (database: string, params: { query: string; compartment?: string; limit?: number; cursor?: string }) =>
  useQuery({ queryKey: keys.search(database, 'elementary-flows', params), queryFn: () => api.searchElementaryFlows(database, params), enabled: params.query.length > 0, ...forever })
export const useSearchMethods = (database: string, params: { query: string; limit?: number; cursor?: string }) =>
  useQuery({ queryKey: keys.search(database, 'methods', params), queryFn: () => api.searchMethods(database, params), enabled: params.query.length > 0, ...forever })
export const useImpact = (id: string, hash: string, body: ImpactArguments, enabled = true, started: () => boolean = () => false) =>
  useQuery({ queryKey: keys.impact(id, hash, body), queryFn: () => api.impact(id, body, started()), enabled, ...forever })
export const useCalculations = (id: string, enabled = true) => useQuery({ queryKey: keys.calculations(id), queryFn: () => api.calculations(id), enabled, ...forever })
export const useContributions = (id: string, hash: string, body: ContributionArguments, enabled = true) =>
  useQuery({ queryKey: keys.contributions(id, hash, body), queryFn: () => api.contributions(id, body), enabled, ...forever })
export const useInventory = (id: string, hash: string, body: InventoryArguments, enabled = true) =>
  useQuery({ queryKey: keys.inventory(id, hash, body), queryFn: () => api.inventory(id, body), enabled, ...forever })
export const useRuns = (id: string, enabled = true) => useQuery({ queryKey: keys.runs(id), queryFn: () => api.runs(id), enabled, ...forever })
export const useRun = (runId: string) => useQuery({ queryKey: keys.run(runId), queryFn: () => api.run(runId), ...forever })
export const useSources = () => useQuery({ queryKey: keys.sources, queryFn: api.sources, ...forever })
export const useInstalls = () => useQuery({ queryKey: keys.installs, queryFn: api.installs, ...forever })
export const useCredentials = () => useQuery({ queryKey: keys.credentials, queryFn: api.credentials, ...forever })
export const useServer = () => useQuery({ queryKey: keys.server, queryFn: api.server, ...forever })

export const useLayout = (id: string, variant: string | null) =>
  useQuery({ queryKey: keys.layout(id, variant), queryFn: ({ signal }) => api.layout(id, variant, signal), ...forever })

export function usePlaceCards(id: string, variant: string | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (placements: { code: string; x: number; y: number }[]) => api.placeCards(id, placements, variant),
    onSuccess: (answer) => {
      client.setQueryData(keys.layout(id, variant), answer)
      void client.invalidateQueries({ queryKey: keys.layouts(id), predicate: (q) => q.queryKey[2] !== variant })
    },
  })
}

export function useReleaseCards(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.releaseCards(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.layouts(id) }),
  })
}

export function usePostRequest(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (draft: RequestDraft) => api.postRequest(id, draft),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.requests(id) })
      void client.invalidateQueries({ queryKey: keys.system(id) })
    },
  })
}

export function useReturnPackage(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, actor, atEntry }: { file: File; actor: string; atEntry: string }) => api.returnPackage(id, file, actor, atEntry),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.system(id) })
      void client.invalidateQueries({ queryKey: keys.log(id) })
    },
  })
}

export function useReturnTables(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, actor }: { file: File; actor: string }) => api.returnTables(id, file, actor),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.system(id) })
      void client.invalidateQueries({ queryKey: keys.log(id) })
      void client.invalidateQueries({ queryKey: keys.parameters(id, null) })
    },
  })
}

export function useCancelRun(runId: string, systemId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.cancelRun(runId),
    onSuccess: (answer) => {
      client.setQueryData(keys.run(runId), answer)
      void client.invalidateQueries({ queryKey: keys.runs(systemId) })
    },
  })
}

export function useStartRun(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: StartRunArguments) => api.startRun(id, body),
    onSuccess: (answer) => {
      client.setQueryData(keys.run(answer.value.id), answer)
      void client.invalidateQueries({ queryKey: keys.runs(id) })
    },
  })
}

export function usePostInstall() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (draft: Omit<InstallDraft, 'actor'>) => api.postInstall(draft),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.installs }),
  })
}

export function useUploadDatabase() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (form: FormData) => api.uploadDatabase(form),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.installs }),
  })
}

export function useCancelInstall() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.cancelInstall(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.installs }),
  })
}

export function usePutCredential() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, account }: { kind: CredentialKind; account: Credential }) => api.putCredential(kind, account),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.credentials })
      void client.invalidateQueries({ queryKey: keys.sources })
    },
  })
}
