"""The domain entities: what a product system holds and what a scenario changes."""

from __future__ import annotations

import difflib
import hashlib
import math
import re
import uuid
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from ecosemantic.errors import Invalid, MethodNotFound, NotFound
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ExchangeInput,
    ForegroundRef,
    SystemRef,
)
from ecosemantic.model.summary import SummaryItem

NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
METADATA_KEYS = ("life_cycle_stage", "hierarchy_level", "supply_chain_tier")

ExchangeType = Literal["production", "product", "elementary"]
UncertaintyType = Literal["lognormal", "normal", "uniform", "triangular"]
Scope = Literal["full", "biosphere_only"]
DISTRIBUTION_IDS: dict[UncertaintyType, int] = {
    "lognormal": 2,
    "normal": 3,
    "uniform": 4,
    "triangular": 5,
}

REQUIRED_PARAMS: dict[str, set[str]] = {
    "lognormal": {"loc", "scale"},
    "normal": {"loc", "scale"},
    "uniform": {"minimum", "maximum"},
    "triangular": {"minimum", "loc", "maximum"},
}
_OPTIONAL_PARAMS: dict[str, set[str]] = {
    "lognormal": {"negative"},
    "normal": set(),
    "uniform": set(),
    "triangular": set(),
}


class Uncertainty(BaseModel):
    """A distribution on an exchange amount, in stats_arrays field names."""

    model_config = ConfigDict(frozen=True)

    type: UncertaintyType
    params: dict[str, float | bool]

    @model_validator(mode="after")
    def _check_params(self) -> Uncertainty:
        required = REQUIRED_PARAMS[self.type]
        allowed = required | _OPTIONAL_PARAMS[self.type]
        keys = set(self.params)
        if missing := required - keys:
            raise ValueError(f"{self.type} needs {sorted(missing)}")
        if extra := keys - allowed:
            raise ValueError(f"{self.type} does not take {sorted(extra)}")
        for key in keys - {"negative"}:
            if isinstance(self.params[key], bool):
                raise ValueError(f"{key} must be numeric")
        if "negative" in keys and not isinstance(self.params["negative"], bool):
            raise ValueError("negative must be a boolean")
        if "scale" in required and self.params["scale"] <= 0:
            raise ValueError("scale must be > 0")
        if "minimum" in required and not self.params["minimum"] < self.params["maximum"]:
            raise ValueError("minimum must be less than maximum")
        if self.type == "triangular" and not (
            self.params["minimum"] <= self.params["loc"] <= self.params["maximum"]
        ):
            raise ValueError("loc must lie between minimum and maximum")
        return self

    def scaled(self, factor: float) -> Uncertainty:
        """The distribution of the amount multiplied by a factor."""
        p = self.params
        magnitude = abs(factor)
        params: dict[str, float | bool]
        if self.type == "lognormal":
            params = {"loc": float(p["loc"]) + math.log(magnitude), "scale": float(p["scale"])}
            if bool(p.get("negative", False)) != (factor < 0):
                params["negative"] = True
            return Uncertainty(type=self.type, params=params)
        if self.type == "normal":
            params = {"loc": float(p["loc"]) * factor, "scale": float(p["scale"]) * magnitude}
            return Uncertainty(type=self.type, params=params)
        low, high = float(p["minimum"]) * factor, float(p["maximum"]) * factor
        if factor < 0:
            low, high = high, low
        params = {"minimum": low, "maximum": high}
        if self.type == "triangular":
            params["loc"] = float(p["loc"]) * factor
        return Uncertainty(type=self.type, params=params)

    def centre(self) -> float:
        """The amount the distribution is centred on: the lognormal's signed median, the normal's
        mean, the triangular's mode or the uniform's midpoint."""
        p = self.params
        if self.type == "lognormal":
            return (-1.0 if p.get("negative", False) else 1.0) * math.exp(float(p["loc"]))
        if self.type == "uniform":
            return (float(p["minimum"]) + float(p["maximum"])) / 2
        return float(p["loc"])

    def anchored(self, amount: float) -> Uncertainty | None:
        """The distribution moved onto an amount that formulas, parameters or cases resolved,
        keeping its relative spread; an amount of zero samples nothing."""
        if amount == 0:
            return None
        centre = self.centre()
        if centre == 0:
            raise Invalid(f"a {self.type} distribution centred on 0 cannot follow amount {amount}")
        return self.scaled(amount / centre)


class Exchange(BaseModel):
    """A flow into or out of a process."""

    id: uuid.UUID
    type: ExchangeType
    name: str
    amount: float
    unit: str
    input: ExchangeInput | None = None
    formula: str | None = None
    comment: str | None = None
    uncertainty: Uncertainty | None = None

    @model_validator(mode="after")
    def _check_input(self) -> Exchange:
        if self.type == "production":
            if self.input is not None:
                raise ValueError("a production exchange carries no input")
            if self.amount == 0:
                raise ValueError("a production amount cannot be zero")
        elif self.type == "elementary":
            if not isinstance(self.input, ElementaryFlowRef):
                raise ValueError("an elementary exchange needs an elementary flow reference")
        elif not isinstance(self.input, BackgroundRef | ForegroundRef | SystemRef):
            raise ValueError("a technosphere exchange needs a process reference")
        return self


class Process(BaseModel):
    """A foreground process the product system owns."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    code: str
    name: str
    unit: str
    location: str
    reference_product: str
    comment: str | None = None
    metadata: dict[str, JsonValue] = Field(
        default_factory=lambda: {key: None for key in METADATA_KEYS}
    )
    exchanges: list[Exchange] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        if not CODE_RE.match(value):
            raise ValueError("code takes letters, digits, hyphens and underscores")
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def _complete_metadata(cls, value: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
        merged: dict[str, JsonValue] = {key: None for key in METADATA_KEYS}
        merged.update(value or {})
        return merged

    def produces_nothing(self) -> bool:
        """Whether a production exchange of this process states an amount of zero."""
        return any(e.type == "production" and e.amount == 0 for e in self.exchanges)


class Parameter(BaseModel):
    """A named product system value, literal or derived by formula."""

    name: str
    value: float | None = None
    formula: str | None = None
    unit: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not NAME_RE.match(value):
            raise ValueError(f"parameter name must match {NAME_RE.pattern}")
        return value

    @model_validator(mode="after")
    def _value_xor_formula(self) -> Parameter:
        if (self.value is None) == (self.formula is None):
            raise ValueError("provide exactly one of value or formula")
        return self


class Case(BaseModel):
    """A named set of parameter values."""

    name: str
    description: str = ""
    values: dict[str, float]


class ExchangeOverride(BaseModel):
    """One scenario change to an exchange: a new amount, a multiplier, or a new input."""

    kind: Literal["exchange"] = "exchange"
    exchange_id: uuid.UUID
    amount: float | None = Field(default=None, ge=0)
    multiplier: float | None = Field(default=None, ge=0)
    input: ExchangeInput | None = None

    @model_validator(mode="after")
    def _one_action(self) -> ExchangeOverride:
        actions = [self.amount is not None, self.multiplier is not None, self.input is not None]
        if sum(actions) != 1:
            raise ValueError("set exactly one of amount, multiplier or input")
        return self

    @model_validator(mode="after")
    def _a_process_input(self) -> ExchangeOverride:
        if isinstance(self.input, SystemRef):
            raise ValueError("a scenario cannot switch an input to a linked system")
        if isinstance(self.input, ElementaryFlowRef):
            raise ValueError(
                "a scenario switches an input to a process, never to an elementary flow"
            )
        return self


class ParameterOverride(BaseModel):
    """One scenario change to a literal parameter's value."""

    kind: Literal["parameter"] = "parameter"
    name: str
    value: float


Override = Annotated[ExchangeOverride | ParameterOverride, Field(discriminator="kind")]


class Scenario(BaseModel):
    """A named override set pinned to the base hash: the content hash without the cases and
    the database build, so a case written or deleted moves no scenario and `base_hash` is never
    the system's own hash."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    overrides: list[Override] = Field(min_length=1)
    base_hash: str | None = None


def method_id(spec: str) -> str:
    """The opaque id calculation tools take: 'm_' and ten hex characters of the spec's SHA-256."""
    return "m_" + hashlib.sha256(spec.encode("utf-8")).hexdigest()[:10]


class Method(BaseModel):
    """An impact assessment method as the background database names it, with its opaque id."""

    model_config = ConfigDict(frozen=True)

    id: str
    tuple: tuple[str, ...]
    spec: str
    unit: str
    impact_method: str
    impact_category: str
    indicator: str

    def summary_item(self) -> SummaryItem:
        """The method as one item of a summary."""
        return SummaryItem(label=self.spec, detail=self.unit, ref=self.id)

    @model_validator(mode="after")
    def _id_matches_spec(self) -> Method:
        if self.id != method_id(self.spec):
            raise ValueError("id must be method_id(spec)")
        return self

    @classmethod
    def of(cls, key: Sequence[str], unit: str) -> Method:
        """The method a background database registers under a key: the database's prefix, then
        the impact method, the category and the indicator, each blank where the key is shorter.
        A bundle's three-part key names the category and the indicator in one name joined by
        ` > `, as its writer joins them, and is split at the first."""
        spec = " > ".join(key)
        named = key[2].split(" > ", 1) if len(key) == 3 else key[2:]
        parts = [*key[1:2], *named, "", "", ""]
        return cls(
            id=method_id(spec),
            tuple=tuple(key),
            spec=spec,
            unit=unit,
            impact_method=parts[0],
            impact_category=parts[1],
            indicator=parts[2],
        )


_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def _normalised(text: str) -> str:
    return _PUNCTUATION.sub(" ", text.lower()).strip()


def nearest_methods(methods: list[Method], reference: str, limit: int = 5) -> list[Method]:
    """The methods whose specification reads most like the reference, the nearest first."""
    target = _normalised(reference)
    return sorted(
        methods,
        key=lambda m: difflib.SequenceMatcher(None, _normalised(m.spec), target).ratio(),
        reverse=True,
    )[:limit]


def method_named(methods: list[Method], database: str, reference: str) -> Method:
    """The method of a database a reference names by its id or its specification;
    MethodNotFound carries the nearest ones when it names none."""
    for method in methods:
        if reference in (method.id, method.spec):
            return method
    raise MethodNotFound(database, reference, nearest_methods(methods, reference))


class Actor(BaseModel):
    """Who performed a write: an agent, a person, or a service."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["agent", "person", "service"]
    id: str | None = None
    name: str | None = None


class ProductSystem(BaseModel):
    """A foreground model on one background database; its functional unit is one unit of the
    reference process's product."""

    id: uuid.UUID
    name: str
    description: str = ""
    notes: str = ""
    database: Database
    processes: list[Process] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    cases: list[Case] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    reference_process: str | None = None
    hash: str | None = None

    @model_validator(mode="after")
    def _unique_names(self) -> ProductSystem:
        for label, names in (
            ("process codes", [a.code for a in self.processes]),
            ("parameter names", [p.name for p in self.parameters]),
            ("case names", [c.name for c in self.cases]),
            ("scenario names", [s.name for s in self.scenarios]),
        ):
            if len(names) != len(set(names)):
                raise ValueError(f"{label} must be unique")
        shared = self.shared_variant_names()
        if shared:
            raise ValueError(f"cases and scenarios share the names {shared}")
        return self

    @model_validator(mode="after")
    def _reference_is_a_process(self) -> ProductSystem:
        codes = {a.code for a in self.processes}
        if self.reference_process is not None and self.reference_process not in codes:
            raise ValueError(f"reference_process {self.reference_process!r} names no process")
        return self

    @model_validator(mode="after")
    def _links_are_pinned(self) -> ProductSystem:
        for process in self.processes:
            for exchange in process.exchanges:
                link = exchange.input
                if not isinstance(link, SystemRef):
                    continue
                if link.at_hash is None:
                    raise ValueError(f"the link on {process.code!r} names no hash")
                if link.product_system_id == self.id:
                    raise ValueError(f"{self.name} cannot link itself")
        return self

    def process(self, code: str) -> Process:
        """The process with this code, or NotFound."""
        for process in self.processes:
            if process.code == code:
                return process
        raise NotFound(f"no process {code!r} in {self.name!r}")

    def exchange(self, exchange_id: uuid.UUID) -> tuple[Process, Exchange]:
        """The exchange with this id and the process holding it, or NotFound."""
        for process in self.processes:
            for exchange in process.exchanges:
                if exchange.id == exchange_id:
                    return process, exchange
        raise NotFound(f"no exchange {exchange_id} in {self.name!r}")

    def exchange_named(self, exchange_id: uuid.UUID) -> str:
        """The exchange as a person names it, its flow and its process, with its id beside it."""
        process, exchange = self.exchange(exchange_id)
        return f"{exchange.name} ({process.name}) {exchange.id}"

    def scenario(self, name: str) -> Scenario:
        """The scenario with this name, or NotFound."""
        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        raise NotFound(f"no scenario {name!r} in {self.name!r}")

    def case(self, name: str) -> Case:
        """The case with this name, or NotFound."""
        for case in self.cases:
            if case.name == name:
                return case
        raise NotFound(f"no case {name!r} in {self.name!r}")

    def parameter(self, name: str) -> Parameter:
        """The parameter with this name, or NotFound."""
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        raise NotFound(f"no parameter {name!r} in {self.name!r}")

    def shared_variant_names(self) -> list[str]:
        """The names both a case and a scenario carry, which a variant name cannot tell apart."""
        return sorted({c.name for c in self.cases} & {s.name for s in self.scenarios})

    def variant(self, name: str) -> Scenario | Case:
        """The scenario or, failing that, the case with this name; the miss lists both."""
        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        for case in self.cases:
            if case.name == name:
                return case
        names = [s.name for s in self.scenarios] + [c.name for c in self.cases]
        raise NotFound(f"no scenario or case {name!r} in {self.name!r}; it has {names}")


class DemandItem(BaseModel):
    ref: BackgroundRef | ForegroundRef
    amount: float


def state_of(document: ProductSystem) -> str:
    """The hash a stored document was read at."""
    if document.hash is None:
        raise Invalid(f"{document.name} was not read from a store")
    return document.hash
