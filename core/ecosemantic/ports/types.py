"""Every input and output model the ports exchange."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, Generic, Literal, Protocol, TypeVar, assert_never, get_args

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
    ExchangeType,
    Method,
    Person,
    ProductSystem,
    Scope,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    DemandItem,
    ElementaryFlowRef,
    ForegroundRef,
    LinkedProcessRef,
)
from ecosemantic.model.summary import Summary, SummaryItem

T = TypeVar("T")
Source = Literal["mcp", "openlca", "import", "handover", "tables"]
Entity = Literal["product_system", "process", "exchange", "parameter", "case", "scenario"]
RequestKind = Literal["approve", "return", "edit"]
Resolution = Literal["accepted", "overridden"]
Restored = Literal["added", "unchanged"]
FlowType = Literal["emission", "natural resource", "inventory indicator", "economic"]
ListingOrder = Literal["relevance", "name"]
FLOW_TYPES: tuple[str, ...] = get_args(FlowType)
CompartmentName = Literal[
    "air",
    "water",
    "soil",
    "immaterial",
    "natural resource",
    "economic",
    "inventory indicator",
]
COMPARTMENT_NAMES: tuple[str, ...] = get_args(CompartmentName)
FLOW_TYPE_OF: dict[CompartmentName, FlowType] = {
    "air": "emission",
    "water": "emission",
    "soil": "emission",
    "immaterial": "emission",
    "natural resource": "natural resource",
    "economic": "economic",
    "inventory indicator": "inventory indicator",
}
TreeKind = Literal["process", "elementary_flow", "remainder"]
Side = Literal["input", "output"]
InventoryOrder = Literal["compartment", "amount"]
Decomposition = Literal["process", "path", "flow", "stage"]
RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]
OpenStatus = Literal["queued", "running"]
STALE_SECONDS = 60.0
BEAT_SECONDS = STALE_SECONDS / 4

UNIT_PROCESS = "unit process"
SourceName = Literal["openlca", "uslci", "bafu", "ecoinvent"]
CredentialKind = Literal["ecoinvent", "nexus"]
InstallStatus = Literal["queued", "running", "terms", "done", "failed", "cancelled"]
Effect = Literal["read", "write", "delete", "compute"]
Origin = Literal["agent", "view"]
CallOutcome = Literal["ok", "error"]
AGENT_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_INPUT_SUB_COMPARTMENTS: dict[str, frozenset[str]] = {
    "inventory indicator": frozenset({"resource use"}),
}
_OUTPUT_SUB_COMPARTMENTS: dict[str, frozenset[str]] = {
    "inventory indicator": frozenset({"output flow", "waste"}),
}


def side_of(flow_type: FlowType, sub_compartment: str | None) -> Side | None:
    """Which side of a process an elementary flow sits on — a resource drawn, an emission emitted —
    or None when the table names no side for the pair.

    An economic flow is an output except under ecoinvent's `primary production factor`, which is an
    input. Indicator flows follow ecoinvent's sub-compartment, which names the side.
    """
    if flow_type == "natural resource":
        return "input"
    if flow_type == "emission":
        return "output"
    if flow_type == "economic":
        return "input" if sub_compartment == "primary production factor" else "output"
    if sub_compartment in _INPUT_SUB_COMPARTMENTS.get(flow_type, frozenset()):
        return "input"
    if sub_compartment in _OUTPUT_SUB_COMPARTMENTS.get(flow_type, frozenset()):
        return "output"
    return None


def flow_side(flow_type: FlowType, sub_compartment: str | None) -> Side:
    """The side of a process an elementary flow sits on, as `side_of` names it; NotSupported for a
    type and sub-compartment the table names no side for."""
    side = side_of(flow_type, sub_compartment)
    if side is None:
        raise NotSupported(f"no side for a {flow_type!r} flow in {sub_compartment!r}")
    return side


Limit = Annotated[int, Field(ge=1)]


def page_start(cursor: str | None, limit: int) -> int:
    """The offset one page starts at, a limit below one refused and a cursor that is no offset."""
    if limit < 1:
        raise Invalid("limit is at least 1")
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise Invalid(f"cursor {cursor!r} is not an offset")
    return int(cursor)


def page_holding(position: int | None, limit: int) -> int:
    """The offset of the page that holds the row at a 0-based position, counted from the first row
    in steps of limit; 0 for no position."""
    if position is None:
        return 0
    return position - position % limit


class Page(BaseModel, Generic[T]):
    """One page of a listing, its cursors and the number of rows the whole listing holds."""

    items: list[T]
    has_more: bool
    next_cursor: str | None = None
    total: int | None = None
    previous_cursor: str | None = None

    @classmethod
    def at_offset(
        cls,
        items: list[T],
        has_more: bool,
        offset: int,
        limit: int,
        total: int | None = None,
    ) -> Page[T]:
        """A page whose cursors name the pages beside it: the next one when there is more, and the
        one before it past the first row."""
        return cls(
            items=items,
            has_more=has_more,
            next_cursor=str(offset + limit) if has_more else None,
            total=total,
            previous_cursor=str(max(offset - limit, 0)) if offset > 0 else None,
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
    compartment: CompartmentName
    sub_compartment: str | None
    unit: str
    flow_type: FlowType
    cas_number: str | None
    cas_as_published: str | None = None

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
    supplier_location: str | None
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
    compartment: CompartmentName
    sub_compartment: str | None
    unit: str
    flow_type: FlowType
    cas_number: str | None = None
    cas_as_published: str | None = None
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


class SubCompartment(BaseModel):
    """One sub-compartment an elementary flow is filed under, with the flows the database holds
    under it."""

    name: str
    flow_count: int


class Compartment(BaseModel):
    name: CompartmentName
    flow_count: int
    sub_compartments: list[SubCompartment]

    @classmethod
    def tally(cls, placed: Iterable[tuple[CompartmentName, str | None]]) -> list[Compartment]:
        """The compartments the given flows fall in, in name order, each with its flow count and
        the sub-compartments found under it with their counts."""
        counts: dict[CompartmentName, int] = {}
        subs: dict[CompartmentName, dict[str, int]] = {}
        for compartment, sub_compartment in placed:
            counts[compartment] = counts.get(compartment, 0) + 1
            if sub_compartment is not None:
                held = subs.setdefault(compartment, {})
                held[sub_compartment] = held.get(sub_compartment, 0) + 1
        return [
            cls(
                name=name,
                flow_count=counts[name],
                sub_compartments=[
                    SubCompartment(name=sub, flow_count=count)
                    for sub, count in sorted(subs.get(name, {}).items())
                ],
            )
            for name in sorted(counts)
        ]


class Factor(BaseModel):
    """One characterization factor of one indicator: the elementary flow it applies to, as its
    database holds it, and the factor."""

    flow: ElementaryFlowRef
    name: str
    compartment: CompartmentName
    sub_compartment: str | None
    unit: str
    factor: float


class WeightingFactor(BaseModel):
    """One category of a weighting set: the impact method it characterises as its id, the
    normalisation the set gives it and its weight, each as the bundle states it and none when it
    states none."""

    method_id: str
    normalisation: float | None
    weighting: float | None


class WeightingSet(BaseModel):
    """One normalisation and weighting set of an impact method's family: its name, none where the
    bundle names none, the unit of the weighted score it answers in, and one factor per category it
    characterises."""

    impact_method: str
    name: str | None
    unit: str | None
    factors: list[WeightingFactor]


def _factor_order(factor: Factor) -> tuple[str, str, bool, str]:
    """A factor's flow name, its compartment, and whether it carries a sub-compartment before
    the sub-compartment itself."""
    return (
        factor.name,
        factor.compartment,
        factor.sub_compartment is not None,
        factor.sub_compartment or "",
    )


def _holds(factor: Factor, words: Sequence[str]) -> bool:
    """Whether the factor's name, compartment and sub-compartment hold every one of the given
    case-folded words, case-folded together."""
    text = " ".join((factor.name, factor.compartment, factor.sub_compartment or "")).casefold()
    return all(word in text for word in words)


def factor_page(
    factors: Sequence[Factor], query: str | None, limit: int, cursor: str | None
) -> Page[Factor]:
    """One page of an indicator's factors, in flow-name order, then compartment, then
    sub-compartment, a factor in no sub-compartment before one in any; a query keeps the factors
    whose name, compartment and sub-compartment hold every word of it, case-folded."""
    words = [word.casefold() for word in (query or "").split()]
    offset = page_start(cursor, limit)
    matched = [factor for factor in sorted(factors, key=_factor_order) if _holds(factor, words)]
    return Page.at_offset(
        matched[offset : offset + limit],
        len(matched) > offset + limit,
        offset,
        limit,
        total=len(matched),
    )


class Location(BaseModel):
    """A location a background database's processes are in, under the code a filter takes."""

    code: str
    name: str


class DatabaseSummary(BaseModel):
    """The counts a background database holds: its processes, its elementary flows, its
    indicators, the units its processes are in and the locations they are in."""

    processes: int
    elementary_flows: int
    indicators: int
    units: int
    locations: int


class ClassificationScheme(BaseModel):
    """One classification scheme a background database carries, with the processes and distinct
    values recorded under it."""

    scheme: str
    processes: int
    values: int


class ClassificationValue(BaseModel):
    """One classification value as the catalog stores it, `<scheme>: <rest>`, with the processes
    that carry it."""

    value: str
    processes: int


class ClassificationNode(BaseModel):
    """One node of a classification tree: the value it is, its processes alone as `own`, and the
    processes of every value under it as `processes`."""

    id: str
    label: str
    code: str | None
    name: str | None
    value: str | None
    own: int
    processes: int
    children: list[ClassificationNode]


class MethodCategory(BaseModel):
    """The indicators one impact category of a method family holds."""

    name: str
    indicators: list[Method]


class MethodFamily(BaseModel):
    """One impact method's categories, as the explorer lists them."""

    name: str
    categories: list[MethodCategory]


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
    """One method's value, naming the method the answer lists it under."""

    value: float
    unit: str
    method_id: str


def fraction_of(score: float, total: float) -> float | None:
    """A score as a share of the total it is part of; none for a total of zero, which nothing is a
    share of."""
    return None if total == 0 else score / total


VALUE_CHOICES = (
    "A weighted total rests on value choices: its weights state how much the method's authors "
    "judge each category to matter, not a measurement."
)


class Total(BaseModel):
    """One weighting set's total: the set that gives it, named as the bundle names it and none where
    the bundle names none, its place among the family's sets counted from 0, the unit it answers
    in, and the value, none where it gives no total. `categories` names the methods whose scores
    take part and `normalised_by_zero` those the set weights and normalises by 0, which take none.
    `reason` says why a set gives no total, and `value_choices` marks what the weights rest on."""

    impact_method: str
    weighting_set: str | None
    position: int
    unit: str | None
    value: float | None
    categories: list[str]
    normalised_by_zero: list[str]
    reason: str | None
    value_choices: str = VALUE_CHOICES


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
    fraction: float | None


class Cut(BaseModel):
    """What a flat contribution list leaves out: the share of the total the cut-off was set at,
    how many parts fell under it and their share, and how many parts reach it past the list's
    length and their share. A share sums the magnitudes of its parts, as the cut-off compares
    them; `below_score` and `unlisted_score` sum their scores as they are signed, so the listed
    scores plus both make the total. Over a total of 0 a part is no share of it, so the cut-off
    sets aside nothing and both shares are None."""

    cutoff: float
    below: int
    share: float | None
    below_score: float
    unlisted: int
    unlisted_share: float | None
    unlisted_score: float


def listed(scores: Sequence[float], total: float, top_n: int, cutoff: float) -> tuple[int, Cut]:
    """How many of the scores, ranked by falling magnitude, a flat list shows, at most top_n of
    those that reach cutoff, and what it leaves out, each part signed and each share summed in
    magnitude. Over a total of 0 no score is a share of it, so the list shows at most top_n parts,
    the cut-off leaves none out of them and the rest is unlisted, each share none."""
    fractions = [fraction_of(score, total) for score in scores]
    magnitudes = [abs(fraction) for fraction in fractions if fraction is not None]
    reaching = len(scores) if total == 0 else sum(1 for value in magnitudes if value >= cutoff)
    shown = min(top_n, reaching)
    return shown, Cut(
        cutoff=cutoff,
        below=len(scores) - reaching,
        share=None if total == 0 else sum(magnitudes[reaching:]),
        below_score=sum(scores[reaching:]),
        unlisted=reaching - shown,
        unlisted_share=None if total == 0 else sum(magnitudes[shown:reaching]),
        unlisted_score=sum(scores[shown:reaching]),
    )


class Hotspots(BaseModel):
    total: Score
    items: list[Hotspot]
    cut: Cut


class FlowHotspot(BaseModel):
    rank: int
    flow: ElementaryFlowRef
    name: str
    compartment: CompartmentName
    sub_compartment: str | None
    amount: float
    unit: str
    score: float
    fraction: float | None


class FlowHotspots(BaseModel):
    total: Score
    items: list[FlowHotspot]
    cut: Cut


class TreeNode(BaseModel):
    kind: TreeKind = "process"
    ref: BackgroundRef | ForegroundRef | LinkedProcessRef | ElementaryFlowRef | None = None
    name: str
    location: str | None
    score: float
    fraction: float | None
    level: int
    children: list[TreeNode] = Field(default_factory=list)


class Tree(BaseModel):
    total: Score
    root: TreeNode
    truncated: bool


class InputPart(BaseModel):
    """One input of a foreground process and its part of the score."""

    ref: BackgroundRef | LinkedProcessRef
    name: str
    location: str | None
    score: float


class OwnPart(BaseModel):
    """One of the product system's own processes: its direct emissions characterised, its
    inputs, and the sum of both."""

    ref: ForegroundRef
    direct: float
    inputs: list[InputPart]
    score: float


class OwnParts(BaseModel):
    """The score and each own process's part of it, in the product system's process order; the
    parts sum to the total."""

    total: Score
    parts: list[OwnPart]


class InventoryRow(BaseModel):
    flow: ElementaryFlowRef
    name: str
    compartment: CompartmentName
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


N_MIN = 30
ADAPTIVE_N_MIN = 6
N_MAX = 200
MAX_DRAWS = 1000
N_MIN_HELP = (
    "The fewest draws an adaptive run takes, at least 6, the fewest draws a median's interval "
    "needs. It bounds the run with `n_max` and applies only when `n` is unset."
)
N_MAX_HELP = (
    "The most draws an adaptive run takes, between `n_min` and `n_max`. It applies "
    "only when `n` is unset."
)
N_HELP = (
    "The count a run takes, fixed. Unset leaves the run adaptive: it stops between "
    "`n_min` and `n_max` once `rel_se_target` is met."
)


class MonteCarloConfig(BaseModel):
    """What a Monte Carlo samples. `full` samples every exchange that carries a distribution, the
    product system's own and the background database's; `biosphere_only` samples only elementary
    exchanges and holds the technosphere fixed. A product system exchange's distribution is
    centred on the amount its formula, parameters and case resolve, keeping its relative spread,
    so an exchange a case sets to zero samples zero. A background normal distribution whose
    standard deviation exceeds its amount is sampled at its amount; the result counts them in
    `drawn.background.held`. `n` fixes the count; otherwise sampling stops between `n_min` and
    `n_max`, which takes an `n_min` of at least 6, once every category it can measure has a
    median whose relative standard error is under `rel_se_target` and none is left to measure."""

    n_min: int = Field(default=N_MIN, ge=1, le=MAX_DRAWS, description=N_MIN_HELP)
    n_max: int = Field(default=N_MAX, ge=1, le=MAX_DRAWS, description=N_MAX_HELP)
    rel_se_target: float = Field(default=0.05, gt=0.0, le=1.0)
    seed: int = 12345
    scope: Scope = "full"
    n: int | None = Field(default=None, ge=1, le=MAX_DRAWS, description=N_HELP)

    @model_validator(mode="after")
    def _ordered(self) -> MonteCarloConfig:
        if self.n_min > self.n_max:
            raise ValueError("n_min must be <= n_max")
        if self.n is None and self.n_min < ADAPTIVE_N_MIN:
            raise ValueError(
                f"an adaptive run takes n_min of at least {ADAPTIVE_N_MIN}, "
                "the fewest draws a median's interval needs"
            )
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

HISTOGRAM_BINS = 20


class Histogram(BaseModel):
    """Draws counted in bins of equal width from the smallest to the largest. `low` and `high`
    are those two draws, and `counts` holds the twenty bins, so a draw falls in bin
    `min(19, floor((draw - low) / width))` with `width = (high - low) / 20`."""

    low: float
    high: float
    counts: list[int]

    @classmethod
    def of(cls, samples: Sequence[float]) -> Histogram:
        """The histogram of these draws, every one equal falling in the first bin."""
        if not samples:
            raise Invalid("a histogram counts draws; this one has none to count")
        low = min(samples)
        high = max(samples)
        width = (high - low) / HISTOGRAM_BINS
        counts = [0] * HISTOGRAM_BINS
        if width == 0:
            counts[0] = len(samples)
        else:
            for draw in samples:
                counts[min(HISTOGRAM_BINS - 1, int((draw - low) // width))] += 1
        return cls(low=low, high=high, counts=counts)


class MonteCarloCategory(BaseModel):
    """One category's summary over the draws a run kept, and either the draws themselves or
    their histogram. A computed result holds its samples and no histogram; an answer whose
    caller did not ask for the samples carries the histogram in their place."""

    method_id: str
    summary: MonteCarloSummary
    samples: list[float] | None = None
    histogram: Histogram | None = None

    def sampled(self) -> list[float]:
        """The samples, or Invalid when this answer carries none."""
        if self.samples is None:
            raise Invalid("this Monte Carlo answer carries no samples; ask for them with samples")
        return self.samples


class MonteCarloTotal(BaseModel):
    """One weighting set's total over a run's draws: the set's identity as `Total` carries it, each
    draw's weighted sum in short and either the draws themselves or their histogram, and the reason
    a set gives no total."""

    impact_method: str
    weighting_set: str | None
    position: int
    unit: str | None
    categories: list[str]
    normalised_by_zero: list[str]
    summary: MonteCarloSummary | None
    samples: list[float] | None = None
    histogram: Histogram | None = None
    reason: str | None
    value_choices: str = VALUE_CHOICES

    def sampled(self) -> list[float]:
        """The draws, or Invalid when this answer carries none."""
        if self.samples is None:
            raise Invalid("this Monte Carlo total carries no samples; ask for them with samples")
        return self.samples


class DrawnCount(BaseModel):
    """How many of one kind a calculation reaches, how many of them carry a distribution, how many
    of those the run drew, and how many it held at their amount."""

    there: int
    carried: int
    drawn: int
    held: int = 0


class Drawn(BaseModel):
    """What a calculation reached and what of it carried a distribution: the literal parameters
    of the systems it reaches, the foreground's exchanges and the background's rows."""

    parameters: DrawnCount
    foreground: DrawnCount
    background: DrawnCount


class MonteCarloResult(BaseModel):
    """The samples of every category over the database build `database` names, and why sampling
    stopped: at the target relative standard error of every median it can measure, at the ceiling
    `n_max`, at a stated count, or cancelled.
    `gating_method` is the id of the method of the category that held the run longest, the one
    whose median's relative standard error was above the target at the latest check that found
    one; a run of a stated count names none, and so does one no category ever held.
    `constant` names the categories met as constant, every draw equal, and
    `indistinguishable_from_zero` those left out of the stop rule, their median's 95 % interval
    holding 0, both in method order and each judged at the run's end. `drawn` states how many
    parameters, foreground exchanges and background rows the calculation reaches, how many of
    them carry a distribution, how many of those the run drew and how many it held at their
    amount: a wide background normal, whose standard deviation exceeds it.
    `credit_loops` names the processes of each loop holding a credit, whose delivery no check
    decides. `dropped_draws` are the draws, counted from zero, left out because a loop without a
    credit, or a process using its own product, delivered nothing in them; `dropped_loops` names
    those loops, and `dropped_background` the background process each failing background loop
    scaled most negatively, or that used as much of its own product as it made. The linked
    fields name those loops inside linked systems. `n` counts the draws kept, and each
    category's samples follow them in order; `without_samples` answers the same result with each
    category's and each total's histogram in place of its draws. `totals` holds one total per
    weighting set of the run's method family, each draw's weighted sum in short; no total takes
    part in the stop rule."""

    database: Database
    n: int
    stopped: Stopped
    gating_method: str | None
    constant: list[str]
    indistinguishable_from_zero: list[str]
    scope: Scope
    drawn: Drawn
    credit_loops: list[list[str]]
    dropped_draws: list[int]
    dropped_loops: list[list[str]]
    dropped_background: list[str]
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    dropped_linked_loops: list[LinkedLoop] = Field(default_factory=list)
    categories: list[MonteCarloCategory]
    totals: list[MonteCarloTotal] = Field(default_factory=list)

    def draws(self) -> list[int]:
        """The draw, counted from zero, each sample was taken at."""
        dropped = set(self.dropped_draws)
        return [d for d in range(self.n + len(dropped)) if d not in dropped]

    def without_samples(self) -> MonteCarloResult:
        """A copy whose every category and every total carries its summary and the histogram of its
        draws, with no samples."""
        return self.model_copy(
            update={
                "categories": [
                    category.model_copy(
                        update={"samples": None, "histogram": Histogram.of(category.sampled())}
                    )
                    for category in self.categories
                ],
                "totals": [
                    total.model_copy(
                        update={"samples": None, "histogram": Histogram.of(total.sampled())}
                    )
                    if total.samples is not None
                    else total
                    for total in self.totals
                ],
            }
        )


class RunProgress(BaseModel):
    """How far a sampling run has got: the draws taken and the largest relative standard error
    among the categories it can measure, None while it can measure none. The total is unknown
    until the stop rule stops."""

    iterations: int = 0
    worst_rel_se: float | None = None


class RunDraft(BaseModel):
    """What a caller posts: the key to pin, the sampling to do, each exchange at that key sending a
    positive amount to a treatment, which runs it backwards, and the weighting sets whose totals the
    run answers."""

    product_system_id: uuid.UUID
    at_hash: str
    demand: list[DemandItem] = Field(default_factory=list)
    methods: list[Method] = Field(default_factory=list)
    weighting_sets: list[WeightingSet] = Field(default_factory=list)
    config: MonteCarloConfig
    treatments_run_backwards: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    """One sampling run without what it answered: the key it was computed on, each exchange at
    that key sending a positive amount to a treatment, which runs it backwards, the weighting sets
    its totals answer, and where it got to. A listing answers runs so."""

    id: uuid.UUID
    product_system_id: uuid.UUID
    at_hash: str
    demand: list[DemandItem] = Field(default_factory=list)
    methods: list[Method] = Field(default_factory=list)
    weighting_sets: list[WeightingSet] = Field(default_factory=list)
    config: MonteCarloConfig
    treatments_run_backwards: list[str] = Field(default_factory=list)
    status: RunStatus = "queued"
    progress: RunProgress = Field(default_factory=RunProgress)
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
        return is_open(self.status)

    def cancellation(self) -> RunPatch:
        """The patch that asks this run to stop; Conflict once it has finished."""
        if not self.open:
            raise Conflict(f"run {self.id} cannot be cancelled after it has finished")
        return RunPatch(cancel_requested=True)


class Run(RunState):
    """One sampling run, with what it answered."""

    result: MonteCarloResult | None = None

    def state(self) -> RunState:
        """The run without what it answered."""
        return RunState(**{name: getattr(self, name) for name in RunState.model_fields})


def is_open(status: RunStatus | InstallStatus) -> bool:
    """True while a run or an install may still change: queued or running."""
    return status in get_args(OpenStatus)


def patched[T: BaseModel](record: T, patch: BaseModel) -> T:
    """The record with the fields the patch names replaced, a field named as none included,
    and every other field as it was."""
    named = {name: getattr(patch, name) for name in patch.model_fields_set}
    return record.model_copy(update=named)


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
        return patched(run, self)


class Account(BaseModel):
    """A credential a source's install needs: a username and a password, and the token a Nexus
    account with a second factor also carries. It never renders its secrets."""

    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr
    token: SecretStr | None = None


class AccountName(BaseModel):
    """An account kind's name and the phrase that names one, as Python and the page write them."""

    name: str
    phrase: str


ACCOUNT_NAMES: Mapping[CredentialKind, AccountName] = {
    "ecoinvent": AccountName(name="ecoinvent", phrase="an ecoinvent account"),
    "nexus": AccountName(name="Nexus", phrase="a Nexus account"),
}


class DatabaseSource(BaseModel):
    """A source an install comes from: the versions its profiles pin, the system models it holds,
    the credential it needs, whether it has terms to accept, and whether its credential is held.
    `account` is that credential's name and phrase, none when its install needs no account."""

    name: SourceName
    versions: list[str]
    system_models: list[str]
    credential: CredentialKind | None
    terms: bool
    held: bool = False

    @computed_field
    @property
    def account(self) -> AccountName | None:
        """The name and phrase of the account this source's install needs."""
        return None if self.credential is None else ACCOUNT_NAMES[self.credential]


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
        if self.drop_unlinked and self.source != "openlca":
            raise ValueError(
                f"drop_unlinked applies to an openlca install; a {self.source} install cuts off "
                "the inputs its release lists as provided by no dataset"
            )
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
        return is_open(self.status)

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
        return patched(install, self)


def source_credential(source: SourceName) -> CredentialKind | None:
    """The credential a source's install needs, none when it needs none."""
    match source:
        case "ecoinvent":
            return "ecoinvent"
        case "bafu":
            return "nexus"
        case "openlca" | "uslci":
            return None
        case _:
            assert_never(source)


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


ChangeOp = Literal["add", "update", "delete"]


class Change(BaseModel):
    op: ChangeOp
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
    person: Person | None = Field(default=None, exclude_if=lambda who: who is None)
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


def _person_id(call: Call) -> str | None:
    """The id of the person a call names, or none when it names no person."""
    return None if call.person is None else call.person.id


def trail(calls: Sequence[Call], product_system_id: uuid.UUID, entry_seq: int) -> list[Call]:
    """The calls that led to one log entry: the calls of its agent for its person, after that
    agent's preceding write, through the call that appended the entry. None when no recorded
    call appended it. Two calls that name no person are the same person's."""
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
    of_person = _person_id(wrote)
    own = [call for call in ordered if call.agent == wrote.agent and _person_id(call) == of_person]
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
