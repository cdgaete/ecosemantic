import type {
  Actor,
  Answer,
  Arrangement,
  BackgroundExchange,
  BackgroundProcess,
  BackgroundRef,
  Case,
  Change,
  ContributionResult,
  Database,
  DemandItem,
  ElementaryFlow,
  ElementaryFlowHit,
  ElementaryFlowRef,
  ErrorEnvelope,
  Exchange,
  ExchangeOverride,
  FlowHotspot,
  ForegroundRef,
  Hotspot,
  ImpactResult,
  InventoryListing,
  InventoryRow,
  LinkedProcessRef,
  Listing,
  LogEntry,
  Method,
  MonteCarloCategory,
  MonteCarloConfig,
  MonteCarloResult,
  MonteCarloSummary,
  Outcome,
  Override,
  PairedDelta,
  Parameter,
  ParameterOverride,
  Placement,
  Process,
  ProcessHit,
  ProductSystem,
  Request,
  Run,
  RunProgress,
  Scenario,
  Score,
  SystemCard,
  SystemRead,
  SystemRef,
  Term,
  TreeNode,
  Uncertainty,
  ValidationCase,
  ValidationIssue,
  ValidationReport,
  VariantScores,
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
import inventory from './fixtures/inventory.json'
import backgroundProcess from './fixtures/background_process.json'
import notFound from './fixtures/error_not_found.json'
import run from './fixtures/run.json'
import runs from './fixtures/runs.json'

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
} satisfies Record<keyof Database, true>

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

const PARAMETER_KEYS = { name: true, value: true, formula: true, unit: true, description: true } satisfies Record<keyof Parameter, true>
const CASE_KEYS = { name: true, description: true, values: true } satisfies Record<keyof Case, true>
const EXCHANGE_OVERRIDE_KEYS = { kind: true, exchange_id: true, amount: true, multiplier: true, input: true } satisfies Record<keyof ExchangeOverride, true>
const PARAMETER_OVERRIDE_KEYS = { kind: true, name: true, value: true } satisfies Record<keyof ParameterOverride, true>
const SCENARIO_KEYS = { name: true, description: true, overrides: true, base_hash: true } satisfies Record<keyof Scenario, true>

const ACTOR_KEYS = { kind: true, id: true, name: true } satisfies Record<keyof Actor, true>

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
const INVENTORY_LISTING_KEYS = { ...LISTING_KEYS, database: true, credit_loops: true, linked_credit_loops: true, treatments_run_backwards: true, floor: true, dropped: true } satisfies Record<keyof InventoryListing, true>
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

const SCORE_KEYS = { value: true, unit: true, method: true } satisfies Record<keyof Score, true>

const VARIANT_SCORES_KEYS = { name: true, scores: true, deltas: true, credit_loops: true, linked_credit_loops: true, treatments_run_backwards: true, uncertainty: true, paired_deltas: true } satisfies Record<keyof VariantScores, true>
const PAIRED_DELTA_KEYS = { delta_abs: true, delta_pct: true, delta_ci95: true } satisfies Record<keyof PairedDelta, true>
const MONTE_CARLO_SUMMARY_KEYS = { n: true, mean: true, median: true, median_ci95: true, percentiles: true, rel_se: true } satisfies Record<keyof MonteCarloSummary, true>
const MONTE_CARLO_CATEGORY_KEYS = { method: true, summary: true, samples: true } satisfies Record<keyof MonteCarloCategory, true>
const MONTE_CARLO_RESULT_KEYS = { database: true, n: true, stopped: true, gating_method: true, scope: true, normals_at_amount: true, credit_loops: true, dropped_draws: true, dropped_loops: true, dropped_background: true, linked_credit_loops: true, dropped_linked_loops: true, categories: true } satisfies Record<keyof MonteCarloResult, true>

const IMPACT_RESULT_KEYS = { product_system: true, database: true, scores: true, credit_loops: true, linked_credit_loops: true, links_behind: true, treatments_run_backwards: true, variants: true, uncertainty: true } satisfies Record<keyof ImpactResult, true>

const MONTE_CARLO_CONFIG_KEYS = { n_min: true, n_max: true, rel_se_target: true, seed: true, scope: true, n: true } satisfies Record<keyof MonteCarloConfig, true>
const DEMAND_ITEM_KEYS = { ref: true, amount: true } satisfies Record<keyof DemandItem, true>
const RUN_PROGRESS_KEYS = { iterations: true, worst_rel_se: true } satisfies Record<keyof RunProgress, true>
const RUN_KEYS = {
  id: true,
  product_system_id: true,
  at_hash: true,
  demand: true,
  methods: true,
  config: true,
  treatments_run_backwards: true,
  status: true,
  progress: true,
  result: true,
  error: true,
  posted_at: true,
  started_at: true,
  finished_at: true,
  cancel_requested: true,
  pid: true,
  open: true,
} satisfies Record<keyof Run, true>

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

const CONTRIBUTION_RESULT_KEYS = {
  database: true,
  by: true,
  total: true,
  credit_loops: true,
  linked_credit_loops: true,
  treatments_run_backwards: true,
  processes: true,
  root: true,
  truncated: true,
  flows: true,
} satisfies Record<keyof ContributionResult, true>

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

const ARRANGEMENT_KEYS = { map: true, cards: true, edges: true, troubles: true, score: true, bounds: true, scaling: true } satisfies Record<keyof Arrangement, true>

const PLACEMENT_KEYS = {
  code: true,
  x: true,
  y: true,
  width: true,
  height: true,
  depth: true,
  shown_inputs: true,
  row_height: true,
  held: true,
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
} satisfies Record<keyof ElementaryFlowHit, true>

const BACKGROUND_EXCHANGE_KEYS = {
  input: true,
  type: true,
  side: true,
  reference: true,
  flow: true,
  supplier: true,
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

function expectScoreKeys(score: Score): void {
  expectKeys(score, SCORE_KEYS)
  expectKeys(score.method, METHOD_KEYS)
}

function expectTreeNodeKeys(node: TreeNode): void {
  expectKeys(node, TREE_NODE_KEYS)
  expectRefKeys(node.ref)
  node.children.forEach(expectTreeNodeKeys)
}

function expectRunKeys(run: Run): void {
  expectKeys(run, RUN_KEYS)
  expectKeys(run.progress, RUN_PROGRESS_KEYS)
  expectKeys(run.config, MONTE_CARLO_CONFIG_KEYS)
  run.demand.forEach((item) => {
    expectKeys(item, DEMAND_ITEM_KEYS)
    expectRefKeys(item.ref)
  })
  run.methods.forEach((method) => expectKeys(method, METHOD_KEYS))
  if (run.result) expectKeys(run.result, MONTE_CARLO_RESULT_KEYS)
}

const typedDatabases = databases as Answer<Database[]>
const typedVocabularyImpactMethods = vocabularyImpactMethods as Answer<Term[]>
const typedVocabularyCompartments = vocabularyCompartments as Answer<Term[]>
const typedSearchProcesses = searchProcesses as Listing<ProcessHit>
const typedSearchMethods = searchMethods as Listing<Method>
const typedSearchElementaryFlows = searchElementaryFlows as Listing<ElementaryFlowHit>
const typedElementaryFlow = elementaryFlowFixture as Answer<ElementaryFlow>
const typedSystems = systems as Answer<SystemCard[]>
const typedSystem = systemFixture as SystemRead
const typedLog = log as Answer<LogEntry[]>
const typedValidation = validation as Answer<ValidationReport>
const typedValidationErrors = validationErrors as Answer<ValidationReport>
const typedLayout = layout as unknown as Answer<Arrangement>
const typedRequests = requests as Answer<Request[]>
const typedImpact = impact as Answer<ImpactResult>
const typedImpactMonteCarlo = impactMonteCarlo as unknown as Answer<ImpactResult>
const typedByProcess = byProcess as Answer<ContributionResult>
const typedByFlow = byFlow as Answer<ContributionResult>
const typedByPath = byPath as Answer<ContributionResult>
const typedInventory = inventory as InventoryListing
const typedBackgroundProcess = backgroundProcess as Answer<BackgroundProcess>
const typedNotFound = notFound as ErrorEnvelope
const typedRun = run as unknown as Answer<Run>
const typedRuns = runs as unknown as Answer<Run[]>

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
    typedDatabases.value.forEach((d) => expectKeys(d, DATABASE_KEYS))
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
    expectKeys(typedSearchMethods, LISTING_KEYS)
    typedSearchMethods.items.forEach((method) => expectKeys(method, METHOD_KEYS))
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
      expectKeys(entry.actor, ACTOR_KEYS)
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

  it('the arrangement of the cards', () => {
    expectKeys(typedLayout, ANSWER_KEYS)
    expectKeys(typedLayout.value, ARRANGEMENT_KEYS)
    expect(typedLayout.value.cards.length).toBeGreaterThan(0)
    typedLayout.value.cards.forEach((card) => expectKeys(card, PLACEMENT_KEYS))
  })

  it('requests', () => {
    expectKeys(typedRequests, ANSWER_KEYS)
    typedRequests.value.forEach((request) => {
      expectKeys(request, REQUEST_KEYS)
      expectKeys(request.actor, ACTOR_KEYS)
      if (request.outcome) {
        expectKeys(request.outcome, OUTCOME_KEYS)
        expectKeys(request.outcome.actor, ACTOR_KEYS)
      }
    })
    expect(typedRequests.value.some((r) => r.outcome !== null)).toBe(true)
  })

  it('impact', () => {
    expectKeys(typedImpact, ANSWER_KEYS)
    expectKeys(typedImpact.value, IMPACT_RESULT_KEYS)
    typedImpact.value.scores.forEach(expectScoreKeys)
    expect(typedImpact.value.variants).toEqual([])
    expect(typedImpact.value.uncertainty).toBeNull()
  })

  it('impact with variants and Monte Carlo', () => {
    expectKeys(typedImpactMonteCarlo, ANSWER_KEYS)
    expectKeys(typedImpactMonteCarlo.value, IMPACT_RESULT_KEYS)
    typedImpactMonteCarlo.value.scores.forEach(expectScoreKeys)
    expect(typedImpactMonteCarlo.value.variants.length).toBeGreaterThan(0)
    typedImpactMonteCarlo.value.variants.forEach((variant) => {
      expectKeys(variant, VARIANT_SCORES_KEYS)
      variant.scores.forEach(expectScoreKeys)
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
      expectKeys(uncertainty.gating_method, METHOD_KEYS)
      uncertainty.categories.forEach((category) => {
        expectKeys(category, MONTE_CARLO_CATEGORY_KEYS)
        expectKeys(category.method, METHOD_KEYS)
        expectKeys(category.summary, MONTE_CARLO_SUMMARY_KEYS)
      })
    }
  })

  it('contributions by process', () => {
    expectKeys(typedByProcess, ANSWER_KEYS)
    expectKeys(typedByProcess.value, CONTRIBUTION_RESULT_KEYS)
    expectKeys(typedByProcess.value.total, SCORE_KEYS)
    const processes = typedByProcess.value.processes
    expect(processes).not.toBeNull()
    processes?.forEach((hotspot) => {
      expectKeys(hotspot, HOTSPOT_KEYS)
      expectRefKeys(hotspot.ref)
    })
    expect(typedByProcess.value.root).toBeNull()
    expect(typedByProcess.value.flows).toBeNull()
  })

  it('contributions by flow', () => {
    expectKeys(typedByFlow, ANSWER_KEYS)
    expectKeys(typedByFlow.value, CONTRIBUTION_RESULT_KEYS)
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
    expectKeys(typedByPath.value, CONTRIBUTION_RESULT_KEYS)
    expect(typedByPath.value.root).not.toBeNull()
    if (typedByPath.value.root) expectTreeNodeKeys(typedByPath.value.root)
    expect(typedByPath.value.processes).toBeNull()
    expect(typedByPath.value.flows).toBeNull()
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
    typedRuns.value.forEach(expectRunKeys)
  })

  it('the not-found error envelope', () => {
    expectKeys(typedNotFound, ERROR_ENVELOPE_KEYS)
  })
})
