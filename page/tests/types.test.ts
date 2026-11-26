import type {
  Actor,
  Answer,
  Arrangement,
  BackgroundExchange,
  BackgroundProcess,
  BackgroundRef,
  CardGeometry,
  Case,
  Change,
  ClassificationNode,
  ClassificationScheme,
  Compartment,
  ContributionResult,
  Cut,
  Database,
  DatabaseSummary,
  DemandItem,
  Drawn,
  DrawnCount,
  ElementaryFlow,
  ElementaryFlowHit,
  ElementaryFlowRef,
  ErrorEnvelope,
  Exchange,
  ExchangeOverride,
  Factor,
  FlowHotspot,
  ForegroundRef,
  Hotspot,
  ImpactResult,
  InventoryListing,
  InventoryRow,
  LinkedProcessRef,
  ListedDatabase,
  Listing,
  LogEntry,
  Method,
  MethodCategory,
  MethodFamily,
  MethodListing,
  MonteCarloCategory,
  MonteCarloConfig,
  MonteCarloResult,
  MonteCarloSummary,
  MonteCarloTotal,
  Outcome,
  Override,
  Page,
  PairedDelta,
  Parameter,
  ParameterOverride,
  Placement,
  Process,
  ProcessHit,
  ProductSystem,
  Request,
  Region,
  Run,
  RunState,
  RunProgress,
  Scenario,
  Score,
  SharedSupplier,
  StageInput,
  StagePart,
  StageProcess,
  StageRegions,
  SubCompartment,
  SystemCard,
  SystemRead,
  SystemRef,
  Term,
  Total,
  TreeNode,
  Uncertainty,
  ValidationCase,
  ValidationIssue,
  ValidationReport,
  VariantScores,
  WeightingFactor,
  WeightingSet,
} from '@/api/types'
import databases from './fixtures/databases.json'
import vocabularyImpactMethods from './fixtures/vocabulary_impact_methods.json'
import vocabularyCompartments from './fixtures/vocabulary_compartments.json'
import searchProcesses from './fixtures/search_processes.json'
import searchMethods from './fixtures/search_methods.json'
import searchElementaryFlows from './fixtures/search_elementary_flows.json'
import elementaryFlowFixture from './fixtures/elementary_flow.json'
import systems from './fixtures/systems.json'
import systemFixture from './fixtures/system.json'
import log from './fixtures/log.json'
import validation from './fixtures/validation.json'
import validationErrors from './fixtures/validation_errors.json'
import layout from './fixtures/layout.json'
import requests from './fixtures/requests.json'
import impact from './fixtures/impact.json'
import impactMonteCarlo from './fixtures/impact_monte_carlo.json'
import byProcess from './fixtures/contributions_process.json'
import byFlow from './fixtures/contributions_flow.json'
import byPath from './fixtures/contributions_path.json'
import byStage from './fixtures/contributions_stage.json'
import inventory from './fixtures/inventory.json'
import backgroundProcess from './fixtures/background_process.json'
import notFound from './fixtures/error_not_found.json'
import monteCarlo from './fixtures/monte_carlo.json'
import run from './fixtures/run.json'
import runs from './fixtures/runs.json'
import explorerSummary from './fixtures/explorer_summary.json'
import explorerSchemes from './fixtures/explorer_schemes.json'
import explorerTree from './fixtures/explorer_tree.json'
import explorerProcesses from './fixtures/explorer_processes.json'
import explorerCompartments from './fixtures/explorer_compartments.json'
import explorerFlows from './fixtures/explorer_flows.json'
import explorerMethods from './fixtures/explorer_methods.json'
import explorerFactors from './fixtures/explorer_factors.json'

function expectKeys<T extends object>(value: T, keys: Record<keyof T, true>): void {
  expect(Object.keys(value).sort()).toEqual(Object.keys(keys).sort())
}

const DATABASE_KEYS = {
  name: true,
  elementary_flows: true,
  scheme: true,
  version: true,
  system_model: true,
  fingerprint: true,
  revision: true,
} satisfies Record<keyof Database, true>

const LISTED_DATABASE_KEYS = { ...DATABASE_KEYS, processes: true } satisfies Record<keyof ListedDatabase, true>

const BACKGROUND_REF_KEYS = { kind: true, database: true, id: true } satisfies Record<keyof BackgroundRef, true>
const FOREGROUND_REF_KEYS = { kind: true, code: true } satisfies Record<keyof ForegroundRef, true>
const ELEMENTARY_FLOW_REF_KEYS = { kind: true, database: true, id: true } satisfies Record<keyof ElementaryFlowRef, true>
const SYSTEM_REF_KEYS = { kind: true, product_system_id: true, at_hash: true, case: true } satisfies Record<keyof SystemRef, true>
const LINKED_PROCESS_REF_KEYS = { kind: true, product_system_id: true, at_hash: true, code: true } satisfies Record<keyof LinkedProcessRef, true>

const UNCERTAINTY_KEYS = { type: true, params: true } satisfies Record<keyof Uncertainty, true>

const EXCHANGE_KEYS = {
  id: true,
  type: true,
  name: true,
  amount: true,
  unit: true,
  input: true,
  formula: true,
  comment: true,
  uncertainty: true,
} satisfies Record<keyof Exchange, true>

const PROCESS_KEYS = {
  id: true,
  code: true,
  name: true,
  unit: true,
  location: true,
  reference_product: true,
  comment: true,
  metadata: true,
  exchanges: true,
} satisfies Record<keyof Process, true>

const PRODUCT_SYSTEM_KEYS = {
  id: true,
  name: true,
  description: true,
  notes: true,
  database: true,
  processes: true,
  parameters: true,
  cases: true,
  scenarios: true,
  reference_process: true,
  hash: true,
} satisfies Record<keyof ProductSystem, true>

const PARAMETER_KEYS = { name: true, value: true, formula: true, unit: true, description: true, uncertainty: true } satisfies Record<keyof Parameter, true>
const CASE_KEYS = { name: true, description: true, values: true } satisfies Record<keyof Case, true>
const EXCHANGE_OVERRIDE_KEYS = { kind: true, exchange_id: true, amount: true, multiplier: true, input: true, name: true } satisfies Record<keyof ExchangeOverride, true>
const PARAMETER_OVERRIDE_KEYS = { kind: true, name: true, value: true } satisfies Record<keyof ParameterOverride, true>
const SCENARIO_KEYS = { name: true, description: true, overrides: true, base_hash: true } satisfies Record<keyof Scenario, true>

type ActorWithoutPerson = Omit<Actor, 'on_behalf_of'>
const ACTOR_KEYS = { kind: true, id: true, name: true } satisfies Record<keyof ActorWithoutPerson, true>

function expectActorKeys(actor: ActorWithoutPerson): void {
  expectKeys(actor, ACTOR_KEYS)
}

const CHANGE_KEYS = { op: true, entity: true, id: true, field: true, before: true, after: true } satisfies Record<keyof Change, true>

const LOG_ENTRY_KEYS = {
  seq: true,
  timestamp: true,
  actor: true,
  source: true,
  base_hash: true,
  result_hash: true,
  changes: true,
  message: true,
} satisfies Record<keyof LogEntry, true>

const REQUEST_KEYS = {
  id: true,
  seq: true,
  timestamp: true,
  actor: true,
  kind: true,
  at_hash: true,
  message: true,
  entity: true,
  entity_id: true,
  outcome: true,
  open: true,
} satisfies Record<keyof Request, true>

const OUTCOME_KEYS = { timestamp: true, actor: true, resolution: true, message: true } satisfies Record<keyof Outcome, true>

const SYSTEM_CARD_KEYS = {
  id: true,
  name: true,
  description: true,
  database: true,
  hash: true,
  view_url: true,
} satisfies Record<keyof SystemCard, true>

const ANSWER_KEYS = { value: true, hint: true, view_url: true } satisfies Record<keyof Answer<unknown>, true>
const LISTING_KEYS = { items: true, has_more: true, next_cursor: true, hint: true, view_url: true } satisfies Record<keyof Listing<unknown>, true>
const METHOD_LISTING_KEYS = { ...LISTING_KEYS, weighting_sets: true } satisfies Record<keyof MethodListing, true>
const INVENTORY_LISTING_KEYS = { ...LISTING_KEYS, database: true, credit_loops: true, linked_credit_loops: true, treatments_run_backwards: true, floor: true, dropped: true, variant: true } satisfies Record<keyof InventoryListing, true>
const SYSTEM_READ_KEYS = { value: true, hint: true, view_url: true, open_requests: true } satisfies Record<keyof SystemRead, true>

const METHOD_KEYS = {
  id: true,
  tuple: true,
  spec: true,
  unit: true,
  impact_method: true,
  impact_category: true,
  indicator: true,
} satisfies Record<keyof Method, true>

const SCORE_KEYS = { value: true, unit: true, method_id: true } satisfies Record<keyof Score, true>

const VARIANT_SCORES_KEYS = { name: true, scores: true, deltas: true, totals: true, total_deltas: true, credit_loops: true, linked_credit_loops: true, treatments_run_backwards: true, uncertainty: true, paired_deltas: true } satisfies Record<keyof VariantScores, true>
const PAIRED_DELTA_KEYS = { delta_abs: true, delta_pct: true, delta_ci95: true } satisfies Record<keyof PairedDelta, true>
const DRAWN_COUNT_KEYS = { there: true, carried: true, drawn: true, held: true } satisfies Record<keyof DrawnCount, true>
const DRAWN_KEYS = { parameters: true, foreground: true, background: true } satisfies Record<keyof Drawn, true>
const MONTE_CARLO_SUMMARY_KEYS = { n: true, mean: true, median: true, median_ci95: true, percentiles: true, rel_se: true } satisfies Record<keyof MonteCarloSummary, true>
const MONTE_CARLO_CATEGORY_KEYS = { method_id: true, summary: true, samples: true, histogram: true } satisfies Record<keyof MonteCarloCategory, true>
const MONTE_CARLO_TOTAL_KEYS = { impact_method: true, weighting_set: true, position: true, unit: true, categories: true, normalised_by_zero: true, summary: true, samples: true, histogram: true, reason: true, value_choices: true } satisfies Record<keyof MonteCarloTotal, true>
const TOTAL_KEYS = { impact_method: true, weighting_set: true, position: true, unit: true, value: true, categories: true, normalised_by_zero: true, reason: true, value_choices: true } satisfies Record<keyof Total, true>
const WEIGHTING_FACTOR_KEYS = { method_id: true, normalisation: true, weighting: true } satisfies Record<keyof WeightingFactor, true>
const WEIGHTING_SET_KEYS = { impact_method: true, name: true, unit: true, factors: true } satisfies Record<keyof WeightingSet, true>
const MONTE_CARLO_RESULT_KEYS = { database: true, n: true, stopped: true, gating_method: true, constant: true, indistinguishable_from_zero: true, scope: true, drawn: true, credit_loops: true, dropped_draws: true, dropped_loops: true, dropped_background: true, linked_credit_loops: true, dropped_linked_loops: true, categories: true, totals: true } satisfies Record<keyof MonteCarloResult, true>

const IMPACT_RESULT_KEYS = { product_system: true, database: true, methods: true, scores: true, demand: true, totals: true, credit_loops: true, linked_credit_loops: true, links_behind: true, treatments_run_backwards: true, variants: true, uncertainty: true } satisfies Record<keyof ImpactResult, true>

const MONTE_CARLO_CONFIG_KEYS = { n_min: true, n_max: true, rel_se_target: true, seed: true, scope: true, n: true } satisfies Record<keyof MonteCarloConfig, true>
const DEMAND_ITEM_KEYS = { ref: true, amount: true } satisfies Record<keyof DemandItem, true>
const RUN_PROGRESS_KEYS = { iterations: true, worst_rel_se: true } satisfies Record<keyof RunProgress, true>
const RUN_STATE_KEYS = {
  id: true,
  product_system_id: true,
  at_hash: true,
  demand: true,
  methods: true,
  weighting_sets: true,
  config: true,
  treatments_run_backwards: true,
  status: true,
  progress: true,
  error: true,
  posted_at: true,
  started_at: true,
  finished_at: true,
  cancel_requested: true,
  pid: true,
  open: true,
} satisfies Record<keyof RunState, true>
const RUN_KEYS = { ...RUN_STATE_KEYS, result: true } satisfies Record<keyof Run, true>

const HOTSPOT_KEYS = {
  rank: true,
  ref: true,
  name: true,
  location: true,
  reference_product: true,
  score: true,
  fraction: true,
} satisfies Record<keyof Hotspot, true>

const FLOW_HOTSPOT_KEYS = {
  rank: true,
  flow: true,
  name: true,
  compartment: true,
  sub_compartment: true,
  amount: true,
  unit: true,
  score: true,
  fraction: true,
} satisfies Record<keyof FlowHotspot, true>

const TREE_NODE_KEYS = {
  kind: true,
  ref: true,
  name: true,
  location: true,
  score: true,
  fraction: true,
  level: true,
  children: true,
} satisfies Record<keyof TreeNode, true>

const STAGE_INPUT_KEYS = { kind: true, ref: true, name: true, location: true, score: true, fraction: true } satisfies Record<keyof StageInput, true>

const STAGE_PROCESS_KEYS = {
  ref: true,
  name: true,
  location: true,
  score: true,
  fraction: true,
  direct: true,
  inputs: true,
} satisfies Record<keyof StageProcess, true>

const STAGE_PART_KEYS = { stage: true, score: true, fraction: true, processes: true } satisfies Record<keyof StagePart, true>

const CONTRIBUTION_RESULT_KEYS = {
  database: true,
  by: true,
  method: true,
  total: true,
  credit_loops: true,
  linked_credit_loops: true,
  treatments_run_backwards: true,
  processes: true,
  root: true,
  truncated: true,
  flows: true,
  stages: true,
  cut: true,
  variant: true,
} satisfies Record<keyof ContributionResult, true>

const CUT_KEYS = { cutoff: true, below: true, share: true, below_score: true, unlisted: true, unlisted_share: true, unlisted_score: true } satisfies Record<keyof Cut, true>

const INVENTORY_ROW_KEYS = {
  flow: true,
  name: true,
  compartment: true,
  sub_compartment: true,
  flow_type: true,
  side: true,
  unit: true,
  amount: true,
  source: true,
} satisfies Record<keyof InventoryRow, true>

const ELEMENTARY_FLOW_KEYS = {
  ref: true,
  name: true,
  compartment: true,
  sub_compartment: true,
  unit: true,
  flow_type: true,
  side: true,
  cas_number: true,
  cas_as_published: true,
  synonyms: true,
} satisfies Record<keyof ElementaryFlow, true>

const VALIDATION_CASE_KEYS = { id: true, passed: true, detail: true } satisfies Record<keyof ValidationCase, true>

const VALIDATION_ISSUE_KEYS = { case: true, code: true, message: true, process_codes: true, suggestion: true } satisfies Record<keyof ValidationIssue, true>

const VALIDATION_REPORT_KEYS = {
  is_valid: true,
  target: true,
  roots: true,
  cases: true,
  errors: true,
} satisfies Record<keyof ValidationReport, true>

const ARRANGEMENT_KEYS = { kind: true, map: true, cards: true, edges: true, troubles: true, score: true, bounds: true, scaling: true, stages: true, shared_suppliers: true, card: true } satisfies Record<keyof Arrangement, true>

const STAGE_REGIONS_KEYS = { stage: true, codes: true, regions: true } satisfies Record<keyof StageRegions, true>
const REGION_KEYS = { x: true, y: true, width: true, height: true } satisfies Record<keyof Region, true>
const SHARED_SUPPLIER_KEYS = { code: true, processes: true, stages: true } satisfies Record<keyof SharedSupplier, true>

const CARD_GEOMETRY_KEYS = { width: true, header_height: true, section_padding: true, section_label: true, row_height: true } satisfies Record<keyof CardGeometry, true>

const PLACEMENT_KEYS = {
  code: true,
  x: true,
  y: true,
  width: true,
  height: true,
  depth: true,
  shown_inputs: true,
  shown_outputs: true,
  folded_inputs: true,
  folded_outputs: true,
  held: true,
  placed_by: true,
  inputs: true,
  outputs: true,
  output: true,
  activity: true,
  scaled: true,
} satisfies Record<keyof Placement, true>

const PROCESS_HIT_KEYS = {
  ref: true,
  name: true,
  reference_product: true,
  location: true,
  unit: true,
  relevance: true,
} satisfies Record<keyof ProcessHit, true>

const ELEMENTARY_FLOW_HIT_KEYS = {
  ref: true,
  name: true,
  compartment: true,
  sub_compartment: true,
  unit: true,
  flow_type: true,
  cas_number: true,
  cas_as_published: true,
} satisfies Record<keyof ElementaryFlowHit, true>

const BACKGROUND_EXCHANGE_KEYS = {
  input: true,
  type: true,
  side: true,
  reference: true,
  flow: true,
  supplier: true,
  supplier_location: true,
  amount: true,
  unit: true,
  cut_off: true,
} satisfies Record<keyof BackgroundExchange, true>

const BACKGROUND_PROCESS_KEYS = {
  ref: true,
  name: true,
  reference_product: true,
  location: true,
  unit: true,
  classifications: true,
  comment: true,
  url: true,
  exchanges: true,
} satisfies Record<keyof BackgroundProcess, true>

const PAGE_KEYS = {
  items: true,
  has_more: true,
  next_cursor: true,
  total: true,
  previous_cursor: true,
} satisfies Record<keyof Page<unknown>, true>

const DATABASE_SUMMARY_KEYS = {
  processes: true,
  elementary_flows: true,
  indicators: true,
  units: true,
  locations: true,
} satisfies Record<keyof DatabaseSummary, true>

const CLASSIFICATION_SCHEME_KEYS = { scheme: true, processes: true, values: true } satisfies Record<keyof ClassificationScheme, true>

const CLASSIFICATION_NODE_KEYS = {
  id: true,
  label: true,
  code: true,
  name: true,
  value: true,
  own: true,
  processes: true,
  children: true,
} satisfies Record<keyof ClassificationNode, true>

const SUB_COMPARTMENT_KEYS = { name: true, flow_count: true } satisfies Record<keyof SubCompartment, true>
const COMPARTMENT_KEYS = { name: true, flow_count: true, sub_compartments: true } satisfies Record<keyof Compartment, true>
const METHOD_CATEGORY_KEYS = { name: true, indicators: true } satisfies Record<keyof MethodCategory, true>
const METHOD_FAMILY_KEYS = { name: true, categories: true } satisfies Record<keyof MethodFamily, true>

const FACTOR_KEYS = {
  flow: true,
  name: true,
  compartment: true,
  sub_compartment: true,
  unit: true,
  factor: true,
} satisfies Record<keyof Factor, true>

const TERM_KEYS = { value: true, detail: true } satisfies Record<keyof Term, true>

const ERROR_ENVELOPE_KEYS = { error: true, message: true, details: true } satisfies Record<keyof ErrorEnvelope, true>

function expectRefKeys(ref: BackgroundRef | ForegroundRef | SystemRef | LinkedProcessRef | ElementaryFlowRef | null): void {
  if (ref === null) return
  if (ref.kind === 'background') expectKeys(ref, BACKGROUND_REF_KEYS)
  else if (ref.kind === 'foreground') expectKeys(ref, FOREGROUND_REF_KEYS)
  else if (ref.kind === 'elementary_flow') expectKeys(ref, ELEMENTARY_FLOW_REF_KEYS)
  else if (ref.kind === 'system') expectKeys(ref, SYSTEM_REF_KEYS)
  else expectKeys(ref, LINKED_PROCESS_REF_KEYS)
}

function expectExchangeKeys(exchange: Exchange): void {
  expectKeys(exchange, EXCHANGE_KEYS)
  expectRefKeys(exchange.input)
  if (exchange.uncertainty) expectKeys(exchange.uncertainty, UNCERTAINTY_KEYS)
}

function expectProcessKeys(process: Process): void {
  expectKeys(process, PROCESS_KEYS)
  process.exchanges.forEach(expectExchangeKeys)
}

function expectOverrideKeys(override: Override): void {
  if (override.kind === 'exchange') {
    expectKeys(override, EXCHANGE_OVERRIDE_KEYS)
    expectRefKeys(override.input)
  } else expectKeys(override, PARAMETER_OVERRIDE_KEYS)
}

function expectScoreKeys(score: Score, methods: Method[]): void {
  expectKeys(score, SCORE_KEYS)
  expect(methods.map((method) => method.id)).toContain(score.method_id)
}

function expectContributionKeys(result: ContributionResult): void {
  expectKeys(result, CONTRIBUTION_RESULT_KEYS)
  expectKeys(result.method, METHOD_KEYS)
  expectKeys(result.total, SCORE_KEYS)
  expect(result.total.method_id).toBe(result.method.id)
}

function expectTreeNodeKeys(node: TreeNode): void {
  expectKeys(node, TREE_NODE_KEYS)
  expectRefKeys(node.ref)
  node.children.forEach(expectTreeNodeKeys)
}

function expectClassificationNodeKeys(node: ClassificationNode): void {
  expectKeys(node, CLASSIFICATION_NODE_KEYS)
  node.children.forEach(expectClassificationNodeKeys)
}

function expectWeightingSetKeys(set: WeightingSet): void {
  expectKeys(set, WEIGHTING_SET_KEYS)
  set.factors.forEach((factor) => expectKeys(factor, WEIGHTING_FACTOR_KEYS))
}

function expectTotalKeys(total: Total): void {
  expectKeys(total, TOTAL_KEYS)
}

function expectMonteCarloTotalKeys(total: MonteCarloTotal): void {
  expectKeys(total, MONTE_CARLO_TOTAL_KEYS)
  if (total.summary) expectKeys(total.summary, MONTE_CARLO_SUMMARY_KEYS)
}

function expectRunStateKeys(run: RunState, keys: Record<string, true> = RUN_STATE_KEYS): void {
  expectKeys(run, keys)
  run.weighting_sets.forEach(expectWeightingSetKeys)
  expectKeys(run.progress, RUN_PROGRESS_KEYS)
  expectKeys(run.config, MONTE_CARLO_CONFIG_KEYS)
  run.demand.forEach((item) => {
    expectKeys(item, DEMAND_ITEM_KEYS)
    expectRefKeys(item.ref)
  })
  run.methods.forEach((method) => expectKeys(method, METHOD_KEYS))
}

function expectRunKeys(run: Run): void {
  expectRunStateKeys(run, RUN_KEYS)
  if (run.result) {
    const result = run.result
    const ids = run.methods.map((method) => method.id)
    expectKeys(result, MONTE_CARLO_RESULT_KEYS)
    expectKeys(result.drawn, DRAWN_KEYS)
    for (const count of [result.drawn.parameters, result.drawn.foreground, result.drawn.background]) expectKeys(count, DRAWN_COUNT_KEYS)
    // a run of a stated count names no category as holding it
    if (result.gating_method !== null) expect(ids).toContain(result.gating_method)
    for (const id of [...result.constant, ...result.indistinguishable_from_zero]) expect(ids).toContain(id)
    result.categories.forEach((category) => {
      expectKeys(category, MONTE_CARLO_CATEGORY_KEYS)
      expect(category.histogram).toBeNull()
      expect(ids).toContain(category.method_id)
    })
    result.totals.forEach(expectMonteCarloTotalKeys)
  }
}

const typedDatabases = databases as Answer<ListedDatabase[]>
const typedVocabularyImpactMethods = vocabularyImpactMethods as Answer<Term[]>
const typedVocabularyCompartments = vocabularyCompartments as Answer<Term[]>
const typedSearchProcesses = searchProcesses as Listing<ProcessHit>
const typedSearchMethods = searchMethods as MethodListing
const typedSearchElementaryFlows = searchElementaryFlows as Listing<ElementaryFlowHit>
const typedElementaryFlow = elementaryFlowFixture as Answer<ElementaryFlow>
const typedSystems = systems as Answer<SystemCard[]>
const typedSystem = systemFixture as SystemRead
const typedLog = log as Answer<LogEntry[]>
const typedValidation = validation as Answer<ValidationReport>
const typedValidationErrors = validationErrors as Answer<ValidationReport>
const typedMonteCarlo = monteCarlo as unknown as Answer<MonteCarloConfig>
const typedLayout = layout as unknown as Answer<Arrangement>
const typedRequests = requests as Answer<Request[]>
const typedImpact = impact as Answer<ImpactResult>
const typedImpactMonteCarlo = impactMonteCarlo as unknown as Answer<ImpactResult>
const typedByProcess = byProcess as Answer<ContributionResult>
const typedByFlow = byFlow as Answer<ContributionResult>
const typedByPath = byPath as Answer<ContributionResult>
const typedByStage = byStage as Answer<ContributionResult>
const typedInventory = inventory as InventoryListing
const typedBackgroundProcess = backgroundProcess as Answer<BackgroundProcess>
const typedNotFound = notFound as ErrorEnvelope
const typedRun = run as unknown as Answer<Run>
const typedRuns = runs as unknown as Answer<RunState[]>
const typedExplorerSummary = explorerSummary as Answer<DatabaseSummary>
const typedExplorerSchemes = explorerSchemes as Answer<ClassificationScheme[]>
const typedExplorerTree = explorerTree as Answer<ClassificationNode[]>
const typedExplorerProcesses = explorerProcesses as Answer<Page<ProcessHit>>
const typedExplorerCompartments = explorerCompartments as Answer<Compartment[]>
const typedExplorerFlows = explorerFlows as Answer<Page<ElementaryFlowHit>>
const typedExplorerMethods = explorerMethods as Answer<MethodFamily[]>
const typedExplorerFactors = explorerFactors as Answer<Page<Factor>>

describe('recorded responses', () => {
  it('carry the fields the page reads', () => {
    expect(typedSystem.value.processes.length).toBeGreaterThan(0)
    expect(typedSystem.open_requests).toBe(1)
    expect(typedRequests.value[0].open).toBe(true)
    expect(typedElementaryFlow.value.side).toBe('input')
    expect(new Set(typedInventory.items.map((r) => r.side))).toEqual(new Set(['output']))
    expect(typedImpact.value.scores[0].unit).toBe('kg CO2-Eq')
    expect(typedByPath.value.root?.children.length).toBeGreaterThan(0)
    expect(typedNotFound.error).toBe('not_found')
    expect(typedRun.value.status).toBe('done')
    expect(typedRun.value.result?.n).toBe(6)
  })
})

describe('recorded response keys match the types field for field', () => {
  it('databases', () => {
    expectKeys(typedDatabases, ANSWER_KEYS)
    typedDatabases.value.forEach((d) => expectKeys(d, LISTED_DATABASE_KEYS))
  })

  it('vocabulary', () => {
    expectKeys(typedVocabularyImpactMethods, ANSWER_KEYS)
    typedVocabularyImpactMethods.value.forEach((t) => expectKeys(t, TERM_KEYS))
    expectKeys(typedVocabularyCompartments, ANSWER_KEYS)
    typedVocabularyCompartments.value.forEach((t) => expectKeys(t, TERM_KEYS))
  })

  it('search results', () => {
    expectKeys(typedSearchProcesses, LISTING_KEYS)
    typedSearchProcesses.items.forEach((hit) => {
      expectKeys(hit, PROCESS_HIT_KEYS)
      expectRefKeys(hit.ref)
    })
    expectKeys(typedSearchMethods, METHOD_LISTING_KEYS)
    typedSearchMethods.items.forEach((method) => expectKeys(method, METHOD_KEYS))
    const families = [...new Set(typedSearchMethods.items.map((method) => method.impact_method))].sort()
    expect(Object.keys(typedSearchMethods.weighting_sets).sort()).toEqual(families)
    expectKeys(typedSearchElementaryFlows, LISTING_KEYS)
    typedSearchElementaryFlows.items.forEach((hit) => {
      expectKeys(hit, ELEMENTARY_FLOW_HIT_KEYS)
      expectRefKeys(hit.ref)
    })
  })

  it('one elementary flow by reference', () => {
    expectKeys(typedElementaryFlow, ANSWER_KEYS)
    expectKeys(typedElementaryFlow.value, ELEMENTARY_FLOW_KEYS)
    expectRefKeys(typedElementaryFlow.value.ref)
  })

  it('the system cards and the system whole', () => {
    expectKeys(typedSystems, ANSWER_KEYS)
    typedSystems.value.forEach((card) => expectKeys(card, SYSTEM_CARD_KEYS))
    expectKeys(typedSystem, SYSTEM_READ_KEYS)
    expectKeys(typedSystem.value, PRODUCT_SYSTEM_KEYS)
    expectKeys(typedSystem.value.database, DATABASE_KEYS)
    typedSystem.value.processes.forEach(expectProcessKeys)
    expect(new Set(typedSystem.value.parameters.map((p) => p.formula === null))).toEqual(new Set([true, false]))
    typedSystem.value.parameters.forEach((p) => expectKeys(p, PARAMETER_KEYS))
    expect(typedSystem.value.cases.length).toBeGreaterThan(0)
    typedSystem.value.cases.forEach((c) => expectKeys(c, CASE_KEYS))
    expect(new Set(typedSystem.value.scenarios.flatMap((s) => s.overrides.map((o) => o.kind)))).toEqual(new Set(['exchange', 'parameter']))
    typedSystem.value.scenarios.forEach((scenario) => {
      expectKeys(scenario, SCENARIO_KEYS)
      scenario.overrides.forEach(expectOverrideKeys)
    })
  })

  it('the log and its change entries', () => {
    expectKeys(typedLog, ANSWER_KEYS)
    typedLog.value.forEach((entry) => {
      expectKeys(entry, LOG_ENTRY_KEYS)
      expectActorKeys(entry.actor)
      entry.changes.forEach((change) => expectKeys(change, CHANGE_KEYS))
    })
  })

  it('validation', () => {
    expectKeys(typedValidation, ANSWER_KEYS)
    expectKeys(typedValidation.value, VALIDATION_REPORT_KEYS)
    typedValidation.value.cases.forEach((c) => expectKeys(c, VALIDATION_CASE_KEYS))
    expect(typedValidation.value.errors).toEqual([])
  })

  it('validation that fails', () => {
    expectKeys(typedValidationErrors, ANSWER_KEYS)
    expectKeys(typedValidationErrors.value, VALIDATION_REPORT_KEYS)
    typedValidationErrors.value.cases.forEach((c) => expectKeys(c, VALIDATION_CASE_KEYS))
    expect(typedValidationErrors.value.errors.length).toBeGreaterThan(0)
    typedValidationErrors.value.errors.forEach((e) => expectKeys(e, VALIDATION_ISSUE_KEYS))
  })

  it('the simulation defaults', () => {
    expectKeys(typedMonteCarlo, ANSWER_KEYS)
    expectKeys(typedMonteCarlo.value, MONTE_CARLO_CONFIG_KEYS)
  })

  it('the arrangement of the cards', () => {
    expectKeys(typedLayout, ANSWER_KEYS)
    expectKeys(typedLayout.value, ARRANGEMENT_KEYS)
    expectKeys(typedLayout.value.card, CARD_GEOMETRY_KEYS)
    expect(typedLayout.value.cards.length).toBeGreaterThan(0)
    typedLayout.value.cards.forEach((card) => expectKeys(card, PLACEMENT_KEYS))
    typedLayout.value.stages.forEach((stage) => {
      expectKeys(stage, STAGE_REGIONS_KEYS)
      stage.regions.forEach((region) => expectKeys(region, REGION_KEYS))
    })
    typedLayout.value.shared_suppliers.forEach((supplier) => expectKeys(supplier, SHARED_SUPPLIER_KEYS))
  })

  it('requests', () => {
    expectKeys(typedRequests, ANSWER_KEYS)
    typedRequests.value.forEach((request) => {
      expectKeys(request, REQUEST_KEYS)
      expectActorKeys(request.actor)
      if (request.outcome) {
        expectKeys(request.outcome, OUTCOME_KEYS)
        expectActorKeys(request.outcome.actor)
      }
    })
    expect(typedRequests.value.some((r) => r.outcome !== null)).toBe(true)
  })

  it('impact', () => {
    expectKeys(typedImpact, ANSWER_KEYS)
    expectKeys(typedImpact.value, IMPACT_RESULT_KEYS)
    typedImpact.value.methods.forEach((method) => expectKeys(method, METHOD_KEYS))
    typedImpact.value.scores.forEach((score) => expectScoreKeys(score, typedImpact.value.methods))
    typedImpact.value.totals.forEach(expectTotalKeys)
    expect(typedImpact.value.variants).toEqual([])
    expect(typedImpact.value.uncertainty).toBeNull()
  })

  it('impact with variants and Monte Carlo', () => {
    expectKeys(typedImpactMonteCarlo, ANSWER_KEYS)
    expectKeys(typedImpactMonteCarlo.value, IMPACT_RESULT_KEYS)
    typedImpactMonteCarlo.value.methods.forEach((method) => expectKeys(method, METHOD_KEYS))
    typedImpactMonteCarlo.value.scores.forEach((score) => expectScoreKeys(score, typedImpactMonteCarlo.value.methods))
    expect(typedImpactMonteCarlo.value.variants.length).toBeGreaterThan(0)
    typedImpactMonteCarlo.value.variants.forEach((variant) => {
      expectKeys(variant, VARIANT_SCORES_KEYS)
      variant.scores.forEach((score) => expectScoreKeys(score, typedImpactMonteCarlo.value.methods))
      variant.totals.forEach(expectTotalKeys)
      expect(variant.paired_deltas).toHaveLength(variant.scores.length)
      variant.paired_deltas?.forEach((paired) => expectKeys(paired, PAIRED_DELTA_KEYS))
      expect(variant.uncertainty).not.toBeNull()
      if (variant.uncertainty) {
        expectKeys(variant.uncertainty, MONTE_CARLO_RESULT_KEYS)
        variant.uncertainty.categories.forEach((category) => expectKeys(category.summary, MONTE_CARLO_SUMMARY_KEYS))
      }
    })
    const uncertainty = typedImpactMonteCarlo.value.uncertainty
    expect(uncertainty).not.toBeNull()
    if (uncertainty) {
      expectKeys(uncertainty, MONTE_CARLO_RESULT_KEYS)
      const ids = typedImpactMonteCarlo.value.methods.map((method) => method.id)
      if (uncertainty.gating_method !== null) expect(ids).toContain(uncertainty.gating_method)
      for (const id of [...uncertainty.constant, ...uncertainty.indistinguishable_from_zero]) expect(ids).toContain(id)
      uncertainty.categories.forEach((category) => {
        expectKeys(category, MONTE_CARLO_CATEGORY_KEYS)
        expect(category.histogram).toBeNull()
        expect(typedImpactMonteCarlo.value.methods.map((method) => method.id)).toContain(category.method_id)
        expectKeys(category.summary, MONTE_CARLO_SUMMARY_KEYS)
      })
    }
  })

  it('contributions by process', () => {
    expectKeys(typedByProcess, ANSWER_KEYS)
    expectContributionKeys(typedByProcess.value)
    const processes = typedByProcess.value.processes
    expect(processes).not.toBeNull()
    processes?.forEach((hotspot) => {
      expectKeys(hotspot, HOTSPOT_KEYS)
      expectRefKeys(hotspot.ref)
    })
    expect(typedByProcess.value.root).toBeNull()
    expect(typedByProcess.value.flows).toBeNull()
    if (typedByProcess.value.cut) expectKeys(typedByProcess.value.cut, CUT_KEYS)
  })

  it('contributions by flow', () => {
    expectKeys(typedByFlow, ANSWER_KEYS)
    expectContributionKeys(typedByFlow.value)
    const flows = typedByFlow.value.flows
    expect(flows).not.toBeNull()
    flows?.forEach((hotspot) => {
      expectKeys(hotspot, FLOW_HOTSPOT_KEYS)
      expectKeys(hotspot.flow, ELEMENTARY_FLOW_REF_KEYS)
    })
    expect(typedByFlow.value.processes).toBeNull()
    expect(typedByFlow.value.root).toBeNull()
  })

  it('contributions by path', () => {
    expectKeys(typedByPath, ANSWER_KEYS)
    expectContributionKeys(typedByPath.value)
    expect(typedByPath.value.root).not.toBeNull()
    if (typedByPath.value.root) expectTreeNodeKeys(typedByPath.value.root)
    expect(typedByPath.value.processes).toBeNull()
    expect(typedByPath.value.flows).toBeNull()
    expect(typedByPath.value.cut).toBeNull()
  })

  it('contributions by stage', () => {
    expectKeys(typedByStage, ANSWER_KEYS)
    expectContributionKeys(typedByStage.value)
    const stages = typedByStage.value.stages
    expect(stages).not.toBeNull()
    stages?.forEach((part) => {
      expectKeys(part, STAGE_PART_KEYS)
      part.processes.forEach((process) => {
        expectKeys(process, STAGE_PROCESS_KEYS)
        expectKeys(process.ref, FOREGROUND_REF_KEYS)
        process.inputs.forEach((input) => {
          expectKeys(input, STAGE_INPUT_KEYS)
          if (input.kind === 'remainder') expect(input.ref).toBeNull()
          else expectRefKeys(input.ref)
        })
      })
    })
    expect(typedByStage.value.by).toBe('stage')
    expect(typedByStage.value.processes).toBeNull()
    expect(typedByStage.value.root).toBeNull()
    expect(typedByStage.value.flows).toBeNull()
  })

  it('inventory', () => {
    expectKeys(typedInventory, INVENTORY_LISTING_KEYS)
    typedInventory.items.forEach((row) => {
      expectKeys(row, INVENTORY_ROW_KEYS)
      expectKeys(row.flow, ELEMENTARY_FLOW_REF_KEYS)
      expectRefKeys(row.source)
    })
  })

  it('a background process with its exchanges', () => {
    expectKeys(typedBackgroundProcess, ANSWER_KEYS)
    expectKeys(typedBackgroundProcess.value, BACKGROUND_PROCESS_KEYS)
    expectRefKeys(typedBackgroundProcess.value.ref)
    const exchanges = typedBackgroundProcess.value.exchanges
    expect(exchanges).not.toBeNull()
    exchanges?.forEach((exchange) => {
      expectKeys(exchange, BACKGROUND_EXCHANGE_KEYS)
      if (exchange.input !== null) expectRefKeys(exchange.input)
    })
  })

  it('a run and the runs of a system', () => {
    expectKeys(typedRun, ANSWER_KEYS)
    expectRunKeys(typedRun.value)
    expectKeys(typedRuns, ANSWER_KEYS)
    typedRuns.value.forEach((listed) => expectRunStateKeys(listed))
  })

  it('the explorer’s summary and schemes', () => {
    expectKeys(typedExplorerSummary, ANSWER_KEYS)
    expectKeys(typedExplorerSummary.value, DATABASE_SUMMARY_KEYS)
    expectKeys(typedExplorerSchemes, ANSWER_KEYS)
    typedExplorerSchemes.value.forEach((scheme) => expectKeys(scheme, CLASSIFICATION_SCHEME_KEYS))
  })

  it('a classification tree, a node and its child', () => {
    expectKeys(typedExplorerTree, ANSWER_KEYS)
    expect(typedExplorerTree.value.length).toBeGreaterThan(0)
    typedExplorerTree.value.forEach(expectClassificationNodeKeys)
    const parent = typedExplorerTree.value.find((node) => node.children.length > 0)
    expect(parent).toBeDefined()
    if (!parent) return
    expectKeys(parent, CLASSIFICATION_NODE_KEYS)
    expectKeys(parent.children[0], CLASSIFICATION_NODE_KEYS)
    expect(parent.children[0].id).not.toBe(parent.id)
  })

  it('the processes under a node', () => {
    expectKeys(typedExplorerProcesses, ANSWER_KEYS)
    expectKeys(typedExplorerProcesses.value, PAGE_KEYS)
    typedExplorerProcesses.value.items.forEach((hit) => {
      expectKeys(hit, PROCESS_HIT_KEYS)
      expectRefKeys(hit.ref)
    })
    expect(typedExplorerProcesses.value.items.length).toBeGreaterThan(0)
  })

  it('the compartments and their sub-compartments', () => {
    expectKeys(typedExplorerCompartments, ANSWER_KEYS)
    typedExplorerCompartments.value.forEach((compartment) => {
      expectKeys(compartment, COMPARTMENT_KEYS)
      compartment.sub_compartments.forEach((sub) => expectKeys(sub, SUB_COMPARTMENT_KEYS))
    })
    expect(typedExplorerCompartments.value.some((compartment) => compartment.sub_compartments.length > 0)).toBe(true)
  })

  it('the flows in a compartment', () => {
    expectKeys(typedExplorerFlows, ANSWER_KEYS)
    expectKeys(typedExplorerFlows.value, PAGE_KEYS)
    typedExplorerFlows.value.items.forEach((hit) => {
      expectKeys(hit, ELEMENTARY_FLOW_HIT_KEYS)
      expectRefKeys(hit.ref)
    })
    expect(typedExplorerFlows.value.items.length).toBeGreaterThan(0)
  })

  it('the method tree and an indicator’s factors', () => {
    expectKeys(typedExplorerMethods, ANSWER_KEYS)
    typedExplorerMethods.value.forEach((family) => {
      expectKeys(family, METHOD_FAMILY_KEYS)
      family.categories.forEach((category) => {
        expectKeys(category, METHOD_CATEGORY_KEYS)
        category.indicators.forEach((indicator) => expectKeys(indicator, METHOD_KEYS))
      })
    })
    expectKeys(typedExplorerFactors, ANSWER_KEYS)
    expectKeys(typedExplorerFactors.value, PAGE_KEYS)
    typedExplorerFactors.value.items.forEach((factor) => {
      expectKeys(factor, FACTOR_KEYS)
      expectKeys(factor.flow, ELEMENTARY_FLOW_REF_KEYS)
    })
    expect(typedExplorerFactors.value.items.length).toBeGreaterThan(0)
  })

  it('the not-found error envelope', () => {
    expectKeys(typedNotFound, ERROR_ENVELOPE_KEYS)
  })
})
