export type Scheme = 'ecoinvent' | 'olca'
export interface Database {
  name: string
  elementary_flows: string
  scheme: Scheme
  version: string
  system_model: string
  fingerprint: string | null
}
export interface BackgroundRef { kind: 'background'; database: string; id: string }
export interface ForegroundRef { kind: 'foreground'; code: string }
export interface SystemRef { kind: 'system'; product_system_id: string; at_hash: string | null; case: string | null }
export interface LinkedProcessRef { kind: 'linked'; product_system_id: string; at_hash: string; code: string }
export interface LinkedLoop { product_system_id: string; at_hash: string; codes: string[] }
export interface ElementaryFlowRef { kind: 'elementary_flow'; database: string; id: string }
export type ExchangeInput = BackgroundRef | ForegroundRef | SystemRef | ElementaryFlowRef
export type ExchangeType = 'production' | 'product' | 'elementary'
export type UncertaintyType = 'lognormal' | 'normal' | 'uniform' | 'triangular'
export interface Uncertainty { type: UncertaintyType; params: Record<string, number | boolean> }
export interface Exchange {
  id: string
  type: ExchangeType
  name: string
  amount: number
  unit: string
  input: ExchangeInput | null
  formula: string | null
  comment: string | null
  uncertainty: Uncertainty | null
}
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json }
export interface Process {
  id: string
  code: string
  name: string
  unit: string
  location: string
  reference_product: string
  comment: string | null
  metadata: Record<string, Json>
  exchanges: Exchange[]
}
export interface Parameter { name: string; value: number | null; formula: string | null; unit: string; description: string }
export interface Case { name: string; description: string; values: Record<string, number> }
export interface CaseRow { parameter: string; values: (number | null)[] }
export interface CaseMatrix { cases: string[]; rows: CaseRow[] }
export interface ParameterSpace { parameters: Parameter[]; values: Record<string, number>; cases: Case[]; matrix: CaseMatrix }
export interface ExchangeOverride {
  kind: 'exchange'
  exchange_id: string
  amount: number | null
  multiplier: number | null
  input: Exclude<ExchangeInput, SystemRef> | null
}
export interface ParameterOverride { kind: 'parameter'; name: string; value: number }
export type Override = ExchangeOverride | ParameterOverride
export interface Scenario {
  name: string
  description: string
  overrides: Override[]
  base_hash: string | null
}
export interface ProductSystem {
  id: string
  name: string
  description: string
  notes: string
  database: Database
  processes: Process[]
  parameters: Parameter[]
  cases: Case[]
  scenarios: Scenario[]
  reference_process: string | null
  hash: string | null
}
export type ActorKind = 'agent' | 'person' | 'service'
export interface Actor { kind: ActorKind; id: string | null; name: string | null }
export type Source = 'mcp' | 'openlca' | 'import' | 'handover' | 'tables'
export type Entity = 'product_system' | 'process' | 'exchange' | 'parameter' | 'case' | 'scenario'
export interface Change {
  op: 'add' | 'update' | 'delete'
  entity: Entity
  id: string
  field: string | null
  before: Json | null
  after: Json | null
}
export interface LogEntry {
  seq: number
  timestamp: string
  actor: Actor
  source: Source
  base_hash: string | null
  result_hash: string
  changes: Change[]
  message: string
}
export type Effect = 'read' | 'write' | 'delete' | 'compute'
export type Origin = 'agent' | 'view'
export interface SummaryItem { label: string; detail: string | null; kind: 'background' | 'elementary_flow' | null; database: string | null; ref: string | null }
export interface SummaryScore { method: string; value: number; unit: string }
export interface Summary { count: number | null; more: boolean; items: SummaryItem[]; scores: SummaryScore[] }
export interface Call {
  id: string
  agent: string
  client: string
  origin: Origin
  tool: string
  effect: Effect
  arguments: { [key: string]: Json }
  product_system_id: string | null
  at_hash: string | null
  entry_seq: number | null
  started_at: string
  duration_ms: number
  outcome: 'ok' | 'error'
  summary: Summary | null
  error: ErrorEnvelope | null
}
export interface AgentSummary { agent: string; client: string; origin: Origin; first_call_at: string; last_call_at: string; calls: number; product_system_id: string | null }
export interface Rerun { result: Json; at_hash: string | null; hash_now: string | null }
export interface Value<T> { value: T }
export type RequestKind = 'approve' | 'return' | 'edit'
export type Resolution = 'accepted' | 'overridden'
export interface Outcome { timestamp: string; actor: Actor; resolution: Resolution; message: string }
export interface Request {
  id: string
  seq: number
  timestamp: string
  actor: Actor
  kind: RequestKind
  at_hash: string
  message: string
  entity: Entity | null
  entity_id: string | null
  outcome: Outcome | null
  open: boolean
}
export interface RequestDraft {
  actor: string
  kind: RequestKind
  at_hash: string
  message: string
  entity?: Entity
  entity_id?: string
}
export interface SystemCard { id: string; name: string; description: string; database: string; hash: string; view_url: string | null }
export interface Answer<T> { value: T; hint: string | null; view_url: string | null }
export interface Listing<T> { items: T[]; has_more: boolean; next_cursor: string | null; hint: string | null; view_url: string | null }
export interface InventoryListing extends Listing<InventoryRow> { database: Database; credit_loops: string[][]; linked_credit_loops: LinkedLoop[]; treatments_run_backwards: string[]; floor: number; dropped: number }
export interface Port { exchange_id: string; y: number }
export interface Placement {
  code: string
  x: number
  y: number
  width: number
  height: number
  depth: number
  shown_inputs: number
  row_height: number
  held: boolean
  inputs: Port[]
  outputs: string[]
  output: number
  activity: number | null
  scaled: Record<string, number> | null
}
export interface Label { x: number; y: number; width: number; height: number; per_unit: string; scaled: string | null; formula: string | null }
export interface Route { provider: string; consumer: string; exchange_id: string; points: [number, number][]; label: Label }
export type TroubleKind = 'cards_overlap' | 'edge_through_card' | 'edges_overlap' | 'edge_backwards' | 'edges_cross' | 'label_overlap'
export interface Trouble { kind: TroubleKind; message: string; codes: string[] }
export interface Arrangement { map: string; cards: Placement[]; edges: Route[]; troubles: Trouble[]; score: number; bounds: Record<string, number>; scaling: string | null }
export interface SystemRead extends Answer<ProductSystem> { open_requests: number }
export interface Method {
  id: string
  tuple: string[]
  spec: string
  unit: string
  impact_method: string
  impact_category: string
  indicator: string
}
export interface Score { value: number; unit: string; method: Method }
export interface PairedDelta { delta_abs: number; delta_pct: number | null; delta_ci95: [number, number] | null }
export interface VariantScores { name: string; scores: Score[]; deltas: number[]; credit_loops: string[][]; linked_credit_loops: LinkedLoop[]; treatments_run_backwards: string[]; uncertainty: MonteCarloResult | null; paired_deltas: PairedDelta[] | null }
export type Scope = 'full' | 'biosphere_only'
export interface MonteCarloConfig { n_min: number; n_max: number; rel_se_target: number; seed: number; scope: Scope; n: number | null }
export interface MonteCarloSummary {
  n: number
  mean: number
  median: number
  median_ci95: [number, number] | null
  percentiles: [number, number]
  rel_se: number | null
}
export interface MonteCarloCategory { method: Method; summary: MonteCarloSummary; samples: number[] }
export type Stopped = 'target' | 'ceiling' | 'fixed' | 'cancelled'
export interface MonteCarloResult { database: Database; n: number; stopped: Stopped; gating_method: Method; scope: Scope; normals_at_amount: number; credit_loops: string[][]; dropped_draws: number[]; dropped_loops: string[][]; dropped_background: string[]; linked_credit_loops: LinkedLoop[]; dropped_linked_loops: LinkedLoop[]; categories: MonteCarloCategory[] }
export interface PinBehind { product_system_id: string; name: string; at_hash: string }
export interface ImpactResult { product_system: string; database: Database; scores: Score[]; credit_loops: string[][]; linked_credit_loops: LinkedLoop[]; links_behind: PinBehind[]; treatments_run_backwards: string[]; variants: VariantScores[]; uncertainty: MonteCarloResult | null }
export type RunStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export interface RunProgress { iterations: number; worst_rel_se: number | null }
export interface Run {
  id: string
  product_system_id: string
  at_hash: string
  demand: DemandItem[]
  methods: Method[]
  config: MonteCarloConfig
  treatments_run_backwards: string[]
  status: RunStatus
  progress: RunProgress
  result: MonteCarloResult | null
  error: ErrorEnvelope | null
  posted_at: string
  started_at: string | null
  finished_at: string | null
  cancel_requested: boolean
  pid: number | null
  open: boolean
}
export interface DemandItem { ref: BackgroundRef | ForegroundRef; amount: number }
export type SourceName = 'openlca' | 'uslci' | 'bafu' | 'ecoinvent'
export type CredentialKind = 'ecoinvent' | 'nexus'
export type InstallStatus = 'queued' | 'running' | 'terms' | 'done' | 'failed' | 'cancelled'
export interface DatabaseSource {
  name: SourceName
  versions: string[]
  system_models: string[]
  credential: CredentialKind | null
  terms: boolean
  held: boolean
}
export interface Credential { username: string; password: string; token?: string }
export interface InstallProgress { step: string; count: number | null }
export interface InstallTerms { licence: string; citation: string }
export interface InstallDraft {
  source: SourceName
  actor: Actor
  version: string | null
  system_model: string | null
  replace: boolean
  accept_terms: boolean
  package: string | null
  name: string | null
  drop_unlinked: boolean
}
export interface Install {
  id: string
  draft: InstallDraft
  status: InstallStatus
  progress: InstallProgress | null
  summary: Record<string, Json> | null
  terms: InstallTerms | null
  error: ErrorEnvelope | null
  posted_at: string
  started_at: string | null
  finished_at: string | null
  cancel_requested: boolean
  pid: number | null
  open: boolean
}
export interface ServerInfo {
  client: { name: string; version: string } | null
  version: string
  data_dir: string
  systems_dir: string
}
export interface Hotspot { rank: number; ref: BackgroundRef | ForegroundRef | LinkedProcessRef; name: string; location: string | null; reference_product: string; score: number; fraction: number }
export interface FlowHotspot { rank: number; flow: ElementaryFlowRef; name: string; compartment: string; amount: number; unit: string; score: number; fraction: number }
export type TreeKind = 'process' | 'elementary_flow' | 'remainder'
export interface TreeNode {
  kind: TreeKind
  ref: BackgroundRef | ForegroundRef | LinkedProcessRef | ElementaryFlowRef | null
  name: string
  location: string | null
  score: number
  fraction: number
  level: number
  children: TreeNode[]
}
export type Decomposition = 'process' | 'path' | 'flow'
export interface ContributionResult {
  database: Database
  by: Decomposition
  total: Score
  credit_loops: string[][]
  linked_credit_loops: LinkedLoop[]
  treatments_run_backwards: string[]
  processes: Hotspot[] | null
  root: TreeNode | null
  truncated: boolean | null
  flows: FlowHotspot[] | null
}
export type FlowType = 'emission' | 'natural resource' | 'inventory indicator' | 'economic'
export type Side = 'input' | 'output'
export interface InventoryRow {
  flow: ElementaryFlowRef
  name: string
  compartment: string
  sub_compartment: string | null
  flow_type: FlowType
  side: Side
  unit: string
  amount: number
  source: ForegroundRef | LinkedProcessRef | null
}
export interface ElementaryFlow {
  ref: ElementaryFlowRef
  name: string
  compartment: string
  sub_compartment: string | null
  unit: string
  flow_type: FlowType
  side: Side
  cas_number: string | null
  synonyms: string[]
}
export interface ValidationCase { id: string; passed: boolean; detail: string | null }
export interface ValidationIssue { case: string; code: string; message: string; process_codes: string[]; suggestion: string }
export interface ValidationReport { is_valid: boolean; target: string | null; roots: string[]; cases: ValidationCase[]; errors: ValidationIssue[] }
export interface ProcessHit { ref: BackgroundRef; name: string; reference_product: string; location: string | null; unit: string; relevance: number }
export interface ElementaryFlowHit {
  ref: ElementaryFlowRef
  name: string
  compartment: string
  sub_compartment: string | null
  unit: string
  flow_type: FlowType
  cas_number: string | null
}
export interface BackgroundExchange {
  input: BackgroundRef | ElementaryFlowRef | null
  type: ExchangeType
  side: Side
  reference: boolean
  flow: string
  supplier: string | null
  amount: number
  unit: string
  cut_off: string | null
}
export interface BackgroundProcess {
  ref: BackgroundRef
  name: string
  reference_product: string
  location: string | null
  unit: string
  classifications: string[]
  comment: string | null
  url: string | null
  exchanges: BackgroundExchange[] | null
}
export type VocabularyKind = 'units' | 'locations' | 'compartments' | 'impact_methods' | 'impact_categories'
export interface Term { value: string; detail: string | null }
export interface ErrorEnvelope { error: string; message: string; details: Record<string, Json> }
export type EventKind = 'entry' | 'request' | 'resolution' | 'deleted' | 'run' | 'call' | 'layout' | 'install'
export interface StreamEvent { kind: EventKind; product_system_id: string | null; entry: LogEntry | null; request: Request | null; run: Run | null; call: Call | null; install: Install | null }
export interface ImpactArguments {
  method_id?: string
  impact_method?: string
  demand?: DemandItem[]
  variants?: string[]
}
export interface ContributionArguments {
  by: Decomposition
  method_id?: string
  impact_method?: string
  demand?: DemandItem[]
  top_n?: number
  max_level?: number
  max_nodes?: number
  cutoff?: number
}
export interface InventoryArguments { demand?: DemandItem[]; compartment?: string; query?: string; limit?: number; cursor?: string }
export interface StartRunArguments { method_id?: string; impact_method?: string; demand?: DemandItem[]; monte_carlo?: Partial<MonteCarloConfig> }
