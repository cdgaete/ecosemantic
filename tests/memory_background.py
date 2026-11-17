"""The fixture background as two ports over its constants, with no Brightway and no index file."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from ecosemantic.errors import NotFound
from ecosemantic.model.entities import Method, method_named
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.search import Phrase, browsed, phrases, spellings
from ecosemantic.ports.terms import tokens
from ecosemantic.ports.types import (
    BackgroundExchange,
    BackgroundProcess,
    ClassificationScheme,
    ClassificationValue,
    Compartment,
    DatabaseSummary,
    ElementaryFlow,
    ElementaryFlowHit,
    Factor,
    FlowType,
    Page,
    ProcessHit,
    factor_page,
    flow_side,
    page_start,
)
from tests.fixture_data import (
    CLASSIFICATIONS,
    CODES,
    FIXTURE_BIO,
    FIXTURE_DATABASE,
    FIXTURE_DB,
    FLOW_IDS,
    FLOWS,
    METHODS,
    PROCESSES,
)


def _compartment(categories: tuple[str, ...]) -> tuple[str, str | None]:
    """The compartment and sub-compartment as a bundle files them: a natural resource under
    openLCA's "Resource"."""
    top = categories[0] if categories else ""
    return "Resource" if top == "natural resource" else top, ("/".join(categories[1:]) or None)


def _flow_type(categories: tuple[str, ...]) -> FlowType:
    return "natural resource" if categories and categories[0] == "natural resource" else "emission"


def _known(database: str) -> None:
    if database not in (FIXTURE_DB, FIXTURE_BIO):
        raise NotFound(f"no database {database!r}; this fixture serves {[FIXTURE_DB]}")


def _stored(key: str) -> list[str]:
    """The classifications of a process as a catalog stores them, each `"<scheme>: <rest>"`, in
    the fixture's order."""
    return [f"{scheme}: {rest}" for scheme, rest in CLASSIFICATIONS.get(key, ())]


def _scheme_of(value: str) -> str:
    """The scheme a stored value is under: what its text holds before the first `": "`."""
    return value.split(": ", 1)[0]


def _listed() -> list[tuple[Method, dict[str, float]]]:
    """The fixture's two methods, built from their keys and units, each with its factors."""
    return [(Method.of(key, unit), factors) for key, unit, factors in METHODS]


def methods() -> list[Method]:
    """The fixture's two methods, built from their keys and units."""
    return [method for method, _ in _listed()]


def _factor(flow: str, factor: float) -> Factor:
    """One of a method's factors as the fixture files it."""
    name, categories, unit = FLOWS[flow]
    compartment, sub_compartment = _compartment(categories)
    return Factor(
        flow=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS[flow]),
        name=name,
        compartment=compartment,
        sub_compartment=sub_compartment,
        unit=unit,
        factor=factor,
    )


def _holds(phrase: Phrase, text: str) -> bool:
    words = tokens(text)
    size = len(phrase.tokens)
    for start in range(len(words) - size + 1):
        window = words[start : start + size]
        if phrase.prefix:
            if window[:-1] == list(phrase.tokens[:-1]) and window[-1].startswith(phrase.tokens[-1]):
                return True
        elif window[0] in spellings(phrase) and window[1:] == list(phrase.tokens[1:]):
            return True
    return False


def _relevance(found: list[Phrase], *fields: str) -> float | None:
    """The number of phrases matched, when the fields match every one of them and there is at
    least one; None otherwise."""
    matched = [any(_holds(phrase, field) for field in fields) for phrase in found]
    return float(len(found)) if found and all(matched) else None


def _browse_relevance(found: list[Phrase] | None, *fields: str) -> float | None:
    """0 when there is no phrase to rank by, so a browsed row matches on its filter alone; the
    number of phrases matched otherwise; None when a phrase the fields do not match is among
    them."""
    return 0.0 if found is None else _relevance(found, *fields)


def _carries(key: str, classifications: Sequence[str]) -> bool:
    """Whether a process carries any of the stored classification values given."""
    stored = _stored(key)
    return any(value in stored for value in classifications)


class MemoryInventory:
    """The fixture background read from its constants."""

    async def list_databases(self) -> list[Database]:
        return [FIXTURE_DATABASE]

    async def get_database(self, name: str) -> Database:
        _known(name)
        return FIXTURE_DATABASE

    async def get_process(self, ref: BackgroundRef, exchanges: bool = False) -> BackgroundProcess:
        key = self._key(ref.id)
        name, product, unit, inputs, emissions = PROCESSES[key]
        return BackgroundProcess(
            ref=ref,
            name=name,
            reference_product=product,
            location="GLO",
            unit=unit,
            classifications=_stored(key),
            url=None,
            exchanges=self._exchanges(inputs, emissions, key) if exchanges else None,
        )

    async def get_elementary_flow(self, ref: ElementaryFlowRef) -> ElementaryFlow:
        key = self._flow_key(ref.id)
        name, categories, unit = FLOWS[key]
        compartment, sub_compartment = _compartment(categories)
        return ElementaryFlow(
            ref=ref,
            name=name,
            compartment=compartment,
            sub_compartment=sub_compartment,
            unit=unit,
            flow_type=_flow_type(categories),
        )

    async def missing(
        self, refs: Sequence[BackgroundRef | ElementaryFlowRef]
    ) -> list[BackgroundRef | ElementaryFlowRef]:
        for ref in refs:
            _known(ref.database)
        held = {"background": set(CODES.values()), "elementary_flow": set(FLOW_IDS.values())}
        return [ref for ref in refs if ref.id not in held[ref.kind]]

    def __init__(self, treating: Collection[str] = ()) -> None:
        # the fixture's processes produce their references; a test names those to treat as
        # treatments
        self.treating = frozenset(treating)

    async def treatments(self, refs: Sequence[BackgroundRef]) -> list[BackgroundRef]:
        for ref in refs:
            _known(ref.database)
        return [ref for ref in refs if ref.id in self.treating]

    async def list_methods(self, database: str, impact_method: str | None = None) -> list[Method]:
        _known(database)
        return [m for m in methods() if impact_method is None or m.impact_method == impact_method]

    async def resolve_method(self, database: str, reference: str) -> Method:
        return method_named(await self.list_methods(database), database, reference)

    async def list_units(self, database: str) -> list[str]:
        _known(database)
        return sorted({unit for _, _, unit, _, _ in PROCESSES.values()})

    async def list_locations(self, database: str) -> list[str]:
        _known(database)
        return ["GLO"]

    async def list_compartments(self, database: str) -> list[Compartment]:
        _known(database)
        return Compartment.tally(_compartment(categories) for _, categories, _ in FLOWS.values())

    async def summarize(self, database: str) -> DatabaseSummary:
        _known(database)
        return DatabaseSummary(
            processes=len(PROCESSES),
            elementary_flows=len(FLOWS),
            indicators=len(METHODS),
            units=len(await self.list_units(database)),
            locations=len(await self.list_locations(database)),
        )

    async def list_classifications(self, database: str) -> list[ClassificationScheme]:
        _known(database)
        covered: dict[str, tuple[set[str], set[str]]] = {}
        for key in PROCESSES:
            for value in _stored(key):
                processes, values = covered.setdefault(_scheme_of(value), (set(), set()))
                processes.add(key)
                values.add(value)
        return [
            ClassificationScheme(scheme=scheme, processes=len(processes), values=len(values))
            for scheme, (processes, values) in sorted(covered.items())
        ]

    async def classification_values(self, database: str, scheme: str) -> list[ClassificationValue]:
        _known(database)
        carried: dict[str, set[str]] = {}
        for key in PROCESSES:
            for value in _stored(key):
                if _scheme_of(value) == scheme:
                    carried.setdefault(value, set()).add(key)
        if not carried:
            raise NotFound(f"no classification scheme {scheme!r} in {database!r}")
        return [
            ClassificationValue(value=value, processes=len(processes))
            for value, processes in sorted(carried.items())
        ]

    async def factors(
        self,
        database: str,
        method_id: str,
        query: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[Factor]:
        _known(database)
        listed = {method.id: factors for method, factors in _listed()}
        if method_id not in listed:
            raise NotFound(f"no method {method_id!r} in {database!r}")
        return factor_page(
            [_factor(flow, value) for flow, value in listed[method_id].items()],
            query,
            limit,
            cursor,
        )

    def _key(self, native_id: str) -> str:
        for key, code in CODES.items():
            if code == native_id:
                return key
        raise NotFound(f"no process {native_id!r} in {FIXTURE_DB!r}")

    def _flow_key(self, flow_id: str) -> str:
        for key, found in FLOW_IDS.items():
            if found == flow_id:
                return key
        raise NotFound(f"no elementary flow {flow_id!r} in {FIXTURE_BIO!r}")

    def _exchanges(
        self, inputs: dict[str, float], emissions: dict[str, float], key: str
    ) -> list[BackgroundExchange]:
        name, product, unit, _, _ = PROCESSES[key]
        return [
            BackgroundExchange(
                input=BackgroundRef(database=FIXTURE_DB, id=CODES[key]),
                type="product",
                side="output",
                reference=True,
                flow=product,
                supplier=None,
                amount=1.0,
                unit=unit,
                cut_off=None,
            ),
            *(
                BackgroundExchange(
                    input=BackgroundRef(database=FIXTURE_DB, id=CODES[provider]),
                    type="product",
                    side="input",
                    reference=False,
                    flow=PROCESSES[provider][1],
                    supplier=PROCESSES[provider][0],
                    amount=amount,
                    unit=PROCESSES[provider][2],
                    cut_off=None,
                )
                for provider, amount in inputs.items()
            ),
            *(
                BackgroundExchange(
                    input=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS[flow]),
                    type="elementary",
                    side=flow_side(_flow_type(FLOWS[flow][1]), _compartment(FLOWS[flow][1])[1]),
                    reference=False,
                    flow=FLOWS[flow][0],
                    supplier=None,
                    amount=amount,
                    unit=FLOWS[flow][2],
                    cut_off=None,
                )
                for flow, amount in emissions.items()
            ),
        ]


class MemorySearch:
    """The fixture background searched over its constants; every row is in memory."""

    async def processes(
        self,
        database: str,
        query: str,
        location: str | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        classifications: Sequence[str] | None = None,
    ) -> Page[ProcessHit]:
        _known(database)
        parsed = browsed(query, classifications is not None)
        offset = page_start(cursor, limit)
        hits = [
            ProcessHit(
                ref=BackgroundRef(database=database, id=CODES[key]),
                name=name,
                reference_product=product,
                location="GLO",
                unit=process_unit,
                relevance=relevance,
            )
            for key, (name, product, process_unit, _, _) in sorted(
                PROCESSES.items(), key=lambda item: item[1][0]
            )
            if (classifications is None or _carries(key, classifications))
            and (relevance := _browse_relevance(parsed, name, product)) is not None
            and (location is None or location == "GLO")
            and (unit is None or unit == process_unit)
        ]
        return Page.at_offset(
            hits[offset : offset + limit], len(hits) > offset + limit, offset, limit
        )

    async def elementary_flows(
        self,
        database: str,
        query: str,
        compartment: str | None = None,
        sub_compartment: str | None = None,
        flow_type: FlowType | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[ElementaryFlowHit]:
        _known(database)
        parsed = browsed(query, compartment is not None or sub_compartment is not None)
        offset = page_start(cursor, limit)
        hits = []
        for key, (name, categories, flow_unit) in sorted(
            FLOWS.items(), key=lambda item: (item[1][0], _compartment(item[1][1])[0])
        ):
            found_compartment, found_sub = _compartment(categories)
            found_type = _flow_type(categories)
            if _browse_relevance(parsed, name, found_compartment, found_sub or "") is None:
                continue
            if any(
                value is not None and value != found
                for value, found in (
                    (compartment, found_compartment),
                    (sub_compartment, found_sub),
                    (flow_type, found_type),
                    (unit, flow_unit),
                )
            ):
                continue
            hits.append(
                ElementaryFlowHit(
                    ref=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS[key]),
                    name=name,
                    compartment=found_compartment,
                    sub_compartment=found_sub,
                    unit=flow_unit,
                    flow_type=found_type,
                    cas_number=None,
                )
            )
        return Page.at_offset(
            hits[offset : offset + limit], len(hits) > offset + limit, offset, limit
        )

    async def methods(
        self, database: str, query: str, limit: int = 20, cursor: str | None = None
    ) -> Page[Method]:
        _known(database)
        parsed = phrases(query)
        hits = [m for m in methods() if _relevance(parsed, m.spec) is not None]
        offset = page_start(cursor, limit)
        return Page.at_offset(
            hits[offset : offset + limit], len(hits) > offset + limit, offset, limit
        )
