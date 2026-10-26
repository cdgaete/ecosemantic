"""The fixture background as two ports over its constants, with no Brightway and no index file."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import Method, method_named
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.types import (
    BackgroundExchange,
    BackgroundProcess,
    Compartment,
    ElementaryFlow,
    ElementaryFlowHit,
    FlowType,
    Page,
    ProcessHit,
    flow_side,
    offset_cursor,
)
from tests.fixture_data import (
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


def methods() -> list[Method]:
    """The fixture's two methods, built from their keys and units."""
    return [Method.of(key, unit) for key, unit, _ in METHODS]


def _terms(query: str) -> list[str]:
    terms = query.lower().split()
    if not terms:
        raise Invalid("a search needs at least one term")
    return terms


def _relevance(terms: list[str], text: str) -> float:
    """How many of the query's terms the text carries; a positive score, not a ranking."""
    return float(sum(1 for term in terms if term in text.lower()))


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
    ) -> Page[ProcessHit]:
        _known(database)
        terms = _terms(query)
        offset = offset_cursor(cursor)
        hits = [
            ProcessHit(
                ref=BackgroundRef(database=database, id=CODES[key]),
                name=name,
                reference_product=product,
                location="GLO",
                unit=process_unit,
                relevance=_relevance(terms, f"{name} {product}"),
            )
            for key, (name, product, process_unit, _, _) in sorted(
                PROCESSES.items(), key=lambda item: item[1][0]
            )
            if all(term in f"{name} {product}".lower() for term in terms)
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
        terms = _terms(query)
        offset = offset_cursor(cursor)
        hits = []
        for key, (name, categories, flow_unit) in sorted(FLOWS.items(), key=lambda i: i[1][0]):
            found_compartment, found_sub = _compartment(categories)
            found_type = _flow_type(categories)
            if not all(term in name.lower() for term in terms):
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
        terms = _terms(query)
        hits = [m for m in methods() if all(t in m.spec.lower() for t in terms)]
        offset = offset_cursor(cursor)
        return Page.at_offset(
            hits[offset : offset + limit], len(hits) > offset + limit, offset, limit
        )
