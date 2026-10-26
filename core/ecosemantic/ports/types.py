"""Every input and output model the ports exchange."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Generic, Literal, Protocol, TypeVar, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    computed_field,
    model_validator,
)

from ecosemantic.errors import Conflict, ErrorEnvelope, Invalid, NotSupported
from ecosemantic.model.entities import (
    Actor,
    DemandItem,
    ExchangeType,
    Method,
    ProductSystem,
    Scope,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    LinkedProcessRef,
)
from ecosemantic.model.summary import Summary, SummaryItem, SummaryScore

T = TypeVar("T")
Source = Literal["mcp", "openlca", "import", "handover", "tables"]
Entity = Literal["product_system", "process", "exchange", "parameter", "case", "scenario"]
RequestKind = Literal["approve", "return", "edit"]
Resolution = Literal["accepted", "overridden"]
Restored = Literal["added", "unchanged"]
FlowType = Literal["emission", "natural resource", "inventory indicator", "economic"]
FLOW_TYPES: tuple[str, ...] = get_args(FlowType)
TreeKind = Literal["process", "elementary_flow", "remainder"]
Side = Literal["input", "output"]
Decomposition = Literal["process", "path", "flow"]
RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]
STALE_SECONDS = 60.0
BEAT_SECONDS = STALE_SECONDS / 4

SourceName = Literal["openlca", "uslci", "bafu", "ecoinvent"]
CredentialKind = Literal["ecoinvent", "nexus"]
InstallStatus = Literal["queued", "running", "terms", "done", "failed", "cancelled"]
Effect = Literal["read", "write", "delete", "compute"]
Origin = Literal["agent", "view"]
CallOutcome = Literal["ok", "error"]
AGENT_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_INPUT_SUB_COMPARTMENTS: dict[str, frozenset[str]] = {
    "inventory indicator": frozenset({"resource use"}),
    "economic": frozenset({"primary production factor"}),
}
_OUTPUT_SUB_COMPARTMENTS: dict[str, frozenset[str]] = {
    "inventory indicator": frozenset({"output flow", "waste"}),
}


def flow_side(flow_type: FlowType, sub_compartment: str | None) -> Side:
    """Which side of a process an elementary flow sits on: a resource is drawn, an emission emitted.

    Indicator and economic flows follow ecoinvent's sub-compartment, which names the side; a pair
    the table does not name is refused.
    """
    if flow_type == "natural resource":
        return "input"
    if flow_type == "emission":
        return "output"
    if sub_compartment in _INPUT_SUB_COMPARTMENTS.get(flow_type, frozenset()):
        return "input"
    if sub_compartment in _OUTPUT_SUB_COMPARTMENTS.get(flow_type, frozenset()):
        return "output"
    raise NotSupported(f"no side for a {flow_type!r} flow in {sub_compartment!r}")


def offset_cursor(cursor: str | None) -> int:
    """The offset a cursor names when the cursor is an offset; none is the start."""
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise Invalid(f"cursor {cursor!r} is not an offset")
    return int(cursor)


class Page(BaseModel, Generic[T]):
    """One page of a listing."""

    items: list[T]
    has_more: bool
    next_cursor: str | None = None

    @classmethod
    def at_offset(cls, items: list[T], has_more: bool, offset: int, limit: int) -> Page[T]:
        """A page whose cursor, when there is more, is the offset of the next one."""
        return cls(
            items=items, has_more=has_more, next_cursor=str(offset + limit) if has_more else None
        )


class ProcessHit(BaseModel):
    ref: BackgroundRef
    name: str
    reference_product: str
    location: str | None
    unit: str
    relevance: float

    def summary_item(self) -> SummaryItem:
        """The hit as one item of a summary, carrying the reference that opens it."""
        return SummaryItem(
            label=self.name,
            detail=self.location,
            kind=self.ref.kind,
            database=self.ref.database,
            ref=self.ref.id,
        )


class ElementaryFlowHit(BaseModel):
    ref: ElementaryFlowRef
    name: str
    compartment: str
    sub_compartment: str | None
    unit: str
    flow_type: FlowType
    cas_number: str | None

    def summary_item(self) -> SummaryItem:
        """The hit as one item of a summary, carrying the reference that opens it."""
        return SummaryItem(
            label=self.name,
            detail=self.compartment,
            kind=self.ref.kind,
            database=self.ref.database,
            ref=self.ref.id,
        )


class BackgroundExchange(BaseModel):
    input: BackgroundRef | ElementaryFlowRef | None
    type: ExchangeType
    side: Side
    reference: bool
    flow: str
    supplier: str | None
    amount: float
    unit: str
    cut_off: str | None


class BackgroundProcess(BaseModel):
    ref: BackgroundRef
    name: str
    reference_product: str
    location: str | None
    unit: str
    classifications: list[str] = Field(default_factory=list)
    comment: str | None = None
    url: str | None = None
    exchanges: list[BackgroundExchange] | None = None

    def summarise(self) -> Summary:
        """The process as the one item an inspection read."""
        item = SummaryItem(
            label=self.name,
            detail=self.location,
            kind=self.ref.kind,
            database=self.ref.database,
            ref=self.ref.id,
        )
        return Summary(count=1, items=[item])


class ElementaryFlow(BaseModel):
    ref: ElementaryFlowRef
    name: str
    compartment: str
    sub_compartment: str | None
    unit: str
    flow_type: FlowType
    cas_number: str | None = None
    synonyms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _placed(self) -> ElementaryFlow:
        flow_side(self.flow_type, self.sub_compartment)
        return self

    @computed_field
    @property
    def side(self) -> Side:
        """Input or output, by the flow's type and sub-compartment."""
        return flow_side(self.flow_type, self.sub_compartment)


class InventoryResult(BaseModel):
    """The inventory's rows, and the amounts set aside as float64 residue: those at or below
    `floor`, a fixed fraction of the largest amount, which `dropped` counts."""

    rows: list[InventoryRow]
    floor: float
    dropped: int


class Compartment(BaseModel):
    name: str
    flow_count: int
    sub_compartments: list[str]

    @classmethod
    def tally(cls, placed: Iterable[tuple[str, str | None]]) -> list[Compartment]:
        """The compartments the given flows fall in, in name order, each with its flow count and
        the sub-compartments found under it. A flow placed in no compartment is not counted."""
        counts: dict[str, int] = {}
        subs: dict[str, set[str]] = {}
        for compartment, sub_compartment in placed:
            if not compartment:
                continue
            counts[compartment] = counts.get(compartment, 0) + 1
            if sub_compartment is not None:
                subs.setdefault(compartment, set()).add(sub_compartment)
        return [
            cls(name=name, flow_count=counts[name], sub_compartments=sorted(subs.get(name, ())))
            for name in sorted(counts)
        ]


class Activity(BaseModel):
    """How many times one foreground process runs to meet a demand."""

    ref: ForegroundRef | LinkedProcessRef
    level: float


class System(BaseModel):
    """What a calculation runs on: a database, the product system calculated on it when there is
    one, with its overrides applied, and each system that one links, read at its pin and
    materialised."""

    database: str
    product_system: ProductSystem | None = None
    linked: dict[uuid.UUID, ProductSystem] = Field(default_factory=dict)

    @classmethod
    def of(
        cls, product_system: ProductSystem, linked: dict[uuid.UUID, ProductSystem] | None = None
    ) -> System:
        """What a calculation on a product system runs on: its database, the system itself and
        the systems it links."""
        return cls(
            database=product_system.database.name,
            product_system=product_system,
            linked=linked or {},
        )


class Score(BaseModel):
    value: float
    unit: str
    method: Method

    def summary_score(self) -> SummaryScore:
        """The score as one line of a summary."""
        return SummaryScore(method=self.method.spec, value=self.value, unit=self.unit)


def fraction_of(score: float, total: float) -> float:
    """A score as a share of the total it is part of; no share of a total of zero."""
    return score / total if total else 0.0


class LinkedLoop(BaseModel):
    """A loop among the processes of a linked product system, with the system and its pin."""

    product_system_id: uuid.UUID
    at_hash: str
    codes: list[str]


class Hotspot(BaseModel):
    rank: int
    ref: BackgroundRef | ForegroundRef | LinkedProcessRef
    name: str
    location: str | None
    reference_product: str
    score: float
    fraction: float


class Hotspots(BaseModel):
    total: Score
    items: list[Hotspot]


class FlowHotspot(BaseModel):
    rank: int
    flow: ElementaryFlowRef
    name: str
    compartment: str
    amount: float
    unit: str
    score: float
    fraction: float


class FlowHotspots(BaseModel):
    total: Score
    items: list[FlowHotspot]


class TreeNode(BaseModel):
    kind: TreeKind = "process"
    ref: BackgroundRef | ForegroundRef | LinkedProcessRef | ElementaryFlowRef | None = None
    name: str
    location: str | None
    score: float
    fraction: float
    level: int
    children: list[TreeNode] = Field(default_factory=list)


class Tree(BaseModel):
    total: Score
    root: TreeNode
    truncated: bool


class InventoryRow(BaseModel):
    flow: ElementaryFlowRef
    name: str
    compartment: str
    sub_compartment: str | None
    flow_type: FlowType
    unit: str
    amount: float
    source: ForegroundRef | LinkedProcessRef | None = None

    @model_validator(mode="after")
    def _placed(self) -> InventoryRow:
        flow_side(self.flow_type, self.sub_compartment)
        return self

    @computed_field
    @property
    def side(self) -> Side:
        """Input or output, by the flow's type and sub-compartment."""
        return flow_side(self.flow_type, self.sub_compartment)


class MonteCarloConfig(BaseModel):
    """What a Monte Carlo samples. `full` samples every exchange that carries a distribution, the
    product system's own and the background database's; `biosphere_only` samples only elementary
    exchanges and holds the technosphere fixed. A product system exchange's distribution is
    centred on the amount its formula, parameters and case resolve, keeping its relative spread,
    so an exchange a case sets to zero samples zero. A background normal distribution whose
    standard deviation exceeds its amount is sampled at its amount; the result counts them in
    `normals_at_amount`. `n` fixes the count; otherwise sampling stops between `n_min` and
    `n_max` once the relative standard error of every category's median is under
    `rel_se_target`, which takes six samples at least."""

    n_min: int = Field(
        default=30,
        ge=1,
        le=1000,
        description=(
            "The fewest draws an adaptive run takes. It bounds the run with `n_max` and "
            "applies only when `n` is unset."
        ),
    )
    n_max: int = Field(
        default=200,
        ge=1,
        le=1000,
        description=(
            "The most draws an adaptive run takes, between `n_min` and `n_max`. It applies "
            "only when `n` is unset."
        ),
    )
    rel_se_target: float = Field(default=0.05, gt=0.0, le=1.0)
    seed: int = 12345
    scope: Scope = "full"
    n: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description=(
            "The count a run takes, fixed. Unset leaves the run adaptive: it stops between "
            "`n_min` and `n_max` once `rel_se_target` is met."
        ),
    )

    @model_validator(mode="after")
    def _ordered(self) -> MonteCarloConfig:
        if self.n_min > self.n_max:
            raise ValueError("n_min must be <= n_max")
        return self


class MonteCarloSummary(BaseModel):
    """One category's samples in short. `median_ci95` is the median's 95 % interval, two of the
    samples that bound it whatever the distribution, which narrows as samples grow, and `rel_se`
    its half-width over 1.96, relative to the median: the stop rule judges it. Both are None below
    six samples, and `rel_se` for a median of zero. `percentiles` are the 2.5th and 97.5th
    percentiles of the samples, the spread of the result itself. `mean` is reported and judged by
    nothing: a loop close to using as much of its products as it makes gives draws whose mean
    need not exist."""

    n: int
    mean: float
    median: float
    median_ci95: tuple[float, float] | None
    percentiles: tuple[float, float]
    rel_se: float | None


Stopped = Literal["target", "ceiling", "fixed", "cancelled"]


class MonteCarloCategory(BaseModel):
    method: Method
    summary: MonteCarloSummary
    samples: list[float]


class MonteCarloResult(BaseModel):
    """The samples of every category over the database build `database` names, and why sampling
    stopped: at the target relative standard error of every median, at the ceiling `n_max`, at a
    stated count, or cancelled.
    `gating_method` is the category whose median's relative standard error is the largest, or
    the first whose is undefined. `normals_at_amount` counts the background normal distributions
    sampled at their amount because their standard deviation exceeds it.
    `credit_loops` names the processes of each loop holding a credit, whose delivery no check
    decides. `dropped_draws` are the draws, counted from zero, left out because a loop without a
    credit, or a process using its own product, delivered nothing in them; `dropped_loops` names
    those loops, and `dropped_background` the background process each failing background loop
    scaled most negatively, or that used as much of its own product as it made. The linked
    fields name those loops inside linked systems. `n` counts the draws kept, and each
    category's samples follow them in order."""

    database: Database
    n: int
    stopped: Stopped
    gating_method: Method
    scope: Scope
    normals_at_amount: int
    credit_loops: list[list[str]]
    dropped_draws: list[int]
    dropped_loops: list[list[str]]
    dropped_background: list[str]
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    dropped_linked_loops: list[LinkedLoop] = Field(default_factory=list)
    categories: list[MonteCarloCategory]

    def draws(self) -> list[int]:
        """The draw, counted from zero, each sample was taken at."""
        dropped = set(self.dropped_draws)
        return [d for d in range(self.n + len(dropped)) if d not in dropped]


class RunProgress(BaseModel):
    """How far a sampling run has got: the draws taken and the largest relative standard error
    of a category's median, None while any is undefined. The total is unknown until the stop
    rule stops."""

    iterations: int = 0
    worst_rel_se: float | None = None


class RunDraft(BaseModel):
    """What a caller posts: the key to pin, the sampling to do, and each exchange at that key
    sending a positive amount to a treatment, which runs it backwards."""

    product_system_id: uuid.UUID
    at_hash: str
    demand: list[DemandItem] = Field(default_factory=list)
    methods: list[Method] = Field(default_factory=list)
    config: MonteCarloConfig
    treatments_run_backwards: list[str] = Field(default_factory=list)


class Run(BaseModel):
    """One sampling run: the key it was computed on, each exchange at that key sending a positive
    amount to a treatment, which runs it backwards, where it got to, and what it answered."""

    id: uuid.UUID
    product_system_id: uuid.UUID
    at_hash: str
    demand: list[DemandItem] = Field(default_factory=list)
    methods: list[Method] = Field(default_factory=list)
    config: MonteCarloConfig
    treatments_run_backwards: list[str] = Field(default_factory=list)
    status: RunStatus = "queued"
    progress: RunProgress = Field(default_factory=RunProgress)
    result: MonteCarloResult | None = None
    error: ErrorEnvelope | None = None
    posted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False
    pid: int | None = None

    @computed_field
    @property
    def open(self) -> bool:
        """True while the run may still change: nothing else is waiting on it."""
        return self.status in ("queued", "running")

    def cancellation(self) -> RunPatch:
        """The patch that asks this run to stop; Conflict once it has finished."""
        if not self.open:
            raise Conflict(f"run {self.id} cannot be cancelled after it has finished")
        return RunPatch(cancel_requested=True)


def refuse_open(runs: Sequence[Run]) -> None:
    """Conflict naming the runs still open, which a delete must not remove from under their
    workers."""
    running = [str(r.id) for r in runs if r.open]
    if running:
        raise Conflict(f"runs {running} are still open; cancel them or wait for them to finish")


class RunPatch(BaseModel):
    """What the worker writes back; only the fields it names are applied."""

    status: RunStatus | None = None
    progress: RunProgress | None = None
    result: MonteCarloResult | None = None
    error: ErrorEnvelope | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool | None = None
    pid: int | None = None

    def applied_to(self, run: Run) -> Run:
        """The run with the fields this patch names replaced, a field named as none included,
        and every other field as it was."""
        named = {name: getattr(self, name) for name in self.model_fields_set}
        return run.model_copy(update=named)


class Account(BaseModel):
    """A credential a source's install needs: a username and a password, and the token a Nexus
    account with a second factor also carries. It never renders its secrets."""

    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr
    token: SecretStr | None = None


class DatabaseSource(BaseModel):
    """A source an install comes from: the versions its profiles pin, the system models it holds,
    the credential it needs, whether it has terms to accept, and whether its credential is held."""

    name: SourceName
    versions: list[str]
    system_models: list[str]
    credential: CredentialKind | None
    terms: bool
    held: bool = False


class InstallProgress(BaseModel):
    """The step an install is on, and that step's count while it has one."""

    step: str
    count: int | None = None


Reporter = Callable[[InstallProgress], None]


class InstallTerms(BaseModel):
    """What an install that stopped at its terms carries: the licence file and the citation to
    read before terms are accepted."""

    licence: str
    citation: str


class InstallDraft(BaseModel):
    """What a caller posts: the source, the version to install, the system model, whether to
    replace what is there, whether the terms are accepted, and the zip an `openlca` install
    reads with the name, version and dropped inputs `setup openlca` takes beside it."""

    source: SourceName
    actor: Actor
    version: str | None = None
    system_model: str | None = None
    replace: bool = False
    accept_terms: bool = False
    package: str | None = None
    name: str | None = None
    drop_unlinked: bool = False

    @model_validator(mode="after")
    def _shaped(self) -> InstallDraft:
        if self.source == "openlca":
            needed = ("package", "name", "version", "system_model")
            lacking = [name for name in needed if not getattr(self, name)]
            if lacking:
                raise ValueError(
                    "an openlca draft needs package, name, version and system_model; "
                    f"it lacks {', '.join(lacking)}"
                )
        if self.source == "ecoinvent" and not (self.version and self.system_model):
            raise ValueError("an ecoinvent draft needs a version and a system model")
        return self


class Install(BaseModel):
    """One install of a database: the draft it was posted from and the actor who posted it, the
    step it is on with that step's count, the summary on success, the terms it stopped at, the
    failure, and its times. It carries no credential."""

    id: uuid.UUID
    draft: InstallDraft
    status: InstallStatus = "queued"
    progress: InstallProgress | None = None
    summary: dict[str, JsonValue] | None = None
    terms: InstallTerms | None = None
    error: ErrorEnvelope | None = None
    posted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False
    pid: int | None = None

    @computed_field
    @property
    def open(self) -> bool:
        """True while the install may still change: queued or running."""
        return self.status in ("queued", "running")

    def cancellation(self) -> InstallPatch:
        """The patch that asks this install to stop; Conflict once it is not open."""
        if not self.open:
            raise Conflict(f"install {self.id} cannot be cancelled after it has finished")
        return InstallPatch(cancel_requested=True)


class InstallPatch(BaseModel):
    """What the install process writes back; only the fields it names are applied."""

    status: InstallStatus | None = None
    progress: InstallProgress | None = None
    summary: dict[str, JsonValue] | None = None
    terms: InstallTerms | None = None
    error: ErrorEnvelope | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool | None = None
    pid: int | None = None

    def applied_to(self, install: Install) -> Install:
        """The install with the fields this patch names replaced, a field named as none
        included, and every other field as it was."""
        named = {name: getattr(self, name) for name in self.model_fields_set}
        return install.model_copy(update=named)


def source_credential(source: SourceName) -> CredentialKind | None:
    """The credential a source's install needs, none when it needs none."""
    if source == "ecoinvent":
        return "ecoinvent"
    if source == "bafu":
        return "nexus"
    return None


class Spot(BaseModel):
    """Where one card was put."""

    x: float
    y: float


class Layout(BaseModel):
    """A product system's arrangement: the cards someone placed, by code. Every other card's
    place is computed, so nothing else is kept."""

    held: dict[str, Spot] = Field(default_factory=dict)


class StoreChange(BaseModel):
    """Something a store changed, named so a reader fetches it for itself: a product system, or
    one run of one."""

    product_system_id: uuid.UUID
    run_id: uuid.UUID | None = None
    gone: bool = False


class Change(BaseModel):
    op: Literal["add", "update", "delete"]
    entity: Entity
    id: str
    field: str | None = None
    before: JsonValue | None = None
    after: JsonValue | None = None


class LogEntry(BaseModel):
    seq: int
    timestamp: datetime
    actor: Actor
    source: Source
    base_hash: str | None
    result_hash: str
    changes: list[Change]
    message: str


class Summarised(Protocol):
    """What a listing reads, which a document carries and so does the record a package keeps."""

    @property
    def id(self) -> uuid.UUID: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def database(self) -> Database: ...

    @property
    def hash(self) -> str | None: ...


class ProductSystemSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    database: str
    hash: str

    @classmethod
    def of(cls, system: Summarised, stored_hash: str | None = None) -> ProductSystemSummary:
        """The listing's view of a document, or of a package's record of one, at the state a
        hash names, its own when unnamed."""
        return cls(
            id=system.id,
            name=system.name,
            description=system.description,
            database=system.database.name,
            hash=stored_hash if stored_hash is not None else (system.hash or ""),
        )


class Outcome(BaseModel):
    """How a request was answered, by whom, and why."""

    timestamp: datetime
    actor: Actor
    resolution: Resolution
    message: str


class RequestDraft(BaseModel):
    """What a person posts; the port assigns the id, the seq and the timestamp."""

    actor: Actor
    kind: RequestKind
    at_hash: str
    message: str
    entity: Entity | None = None
    entity_id: str | None = None

    @model_validator(mode="after")
    def _shaped(self) -> RequestDraft:
        if self.actor.kind != "person":
            raise ValueError("a request is posted by a person")
        names = self.entity is not None and self.entity_id is not None
        if self.kind == "edit" and not names:
            raise ValueError("an edit request names its entity and entity_id")
        if self.kind != "edit" and (self.entity is not None or self.entity_id is not None):
            raise ValueError("only an edit request names an entity")
        return self


class Request(BaseModel):
    """A person's word on a product system, and the agent's answer to it."""

    id: uuid.UUID
    seq: int
    timestamp: datetime
    actor: Actor
    kind: RequestKind
    at_hash: str
    message: str
    entity: Entity | None = None
    entity_id: str | None = None
    outcome: Outcome | None = None

    @computed_field
    @property
    def open(self) -> bool:
        """True while a return or edit request has no outcome; an approval is never open."""
        return self.kind != "approve" and self.outcome is None


def checked_agent(name: str) -> str:
    """The name, when it is one an agent can carry and a file can be named after."""
    if re.fullmatch(AGENT_NAME, name) is None:
        raise Invalid(
            f"{name!r} is not an agent name: 1 to 64 letters, digits, '.', '_' or '-', "
            "starting with a letter or a digit; name the agent with agent=<name> on its URL"
        )
    return name


class CallDraft(BaseModel):
    """One tool call as the recorder saw it; the port assigns the id."""

    agent: str = Field(pattern=AGENT_NAME)
    client: str
    origin: Origin
    tool: str
    effect: Effect
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    product_system_id: uuid.UUID | None = None
    at_hash: str | None = None
    entry_seq: int | None = None
    started_at: datetime
    duration_ms: int
    outcome: CallOutcome
    summary: Summary | None = None
    error: ErrorEnvelope | None = None


class Call(CallDraft):
    """One recorded tool call."""

    id: uuid.UUID


class AgentSummary(BaseModel):
    """One agent the record names: who it is, when it called, and the system it last named."""

    agent: str
    client: str
    origin: Origin
    first_call_at: datetime
    last_call_at: datetime
    calls: int
    product_system_id: uuid.UUID | None = None


def selected(
    calls: Sequence[Call],
    agent: str | None = None,
    product_system_id: uuid.UUID | None = None,
    after: datetime | None = None,
) -> list[Call]:
    """The calls of one agent, about one system, started after a time, in the order they
    started."""
    wanted = checked_agent(agent) if agent is not None else None
    kept = [
        call
        for call in calls
        if (wanted is None or call.agent == wanted)
        and (product_system_id is None or call.product_system_id == product_system_id)
        and (after is None or call.started_at > after)
    ]
    return sorted(kept, key=lambda call: (call.started_at, str(call.id)))


def agents_of(calls: Sequence[Call]) -> list[AgentSummary]:
    """Each agent the calls name, the latest to call first."""
    grouped: dict[str, list[Call]] = {}
    for call in selected(calls):
        grouped.setdefault(call.agent, []).append(call)
    summaries = [
        AgentSummary(
            agent=agent,
            client=own[-1].client,
            origin=own[-1].origin,
            first_call_at=own[0].started_at,
            last_call_at=own[-1].started_at,
            calls=len(own),
            product_system_id=next(
                (c.product_system_id for c in reversed(own) if c.product_system_id is not None),
                None,
            ),
        )
        for agent, own in grouped.items()
    ]
    return sorted(summaries, key=lambda summary: summary.last_call_at, reverse=True)


def trail(calls: Sequence[Call], product_system_id: uuid.UUID, entry_seq: int) -> list[Call]:
    """The calls that led to one log entry: its agent's calls after that agent's preceding
    write, through the call that appended the entry. None when no recorded call appended it."""
    ordered = selected(calls)
    wrote = next(
        (
            call
            for call in ordered
            if call.product_system_id == product_system_id and call.entry_seq == entry_seq
        ),
        None,
    )
    if wrote is None:
        return []
    own = [call for call in ordered if call.agent == wrote.agent]
    end = own.index(wrote)
    start = next((i + 1 for i in range(end - 1, -1, -1) if own[i].entry_seq is not None), 0)
    return own[start : end + 1]


def open_trail(
    calls: Sequence[Call], agent: str, product_system_id: uuid.UUID | None = None
) -> list[Call]:
    """An agent's calls after its latest write: its work in progress. Under one product system,
    the calls that name that system or none, so a call about another system stays out."""
    own = selected(calls, agent=agent)
    start = next((i + 1 for i in range(len(own) - 1, -1, -1) if own[i].entry_seq is not None), 0)
    return [
        call
        for call in own[start:]
        if product_system_id is None or call.product_system_id in (None, product_system_id)
    ]
