"""The inventory port over the catalogs of the store's databases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ecosemantic.backends.native.store import NativeStore
from ecosemantic.errors import NotFound
from ecosemantic.model.entities import ExchangeType, Method, method_named
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.inventory import no_flow
from ecosemantic.ports.types import (
    BackgroundExchange,
    BackgroundProcess,
    ClassificationScheme,
    ClassificationValue,
    Compartment,
    CompartmentName,
    DatabaseSummary,
    ElementaryFlow,
    Factor,
    Location,
    Page,
    WeightingFactor,
    WeightingSet,
    factor_page,
)

_UNITS = "SELECT DISTINCT unit FROM processes"
_LOCATIONS = "SELECT code, name FROM locations ORDER BY code"
_SCHEME = "split_part(value, ': ', 1)"
_CLASSIFICATIONS = (
    f"SELECT {_SCHEME} AS scheme, count(DISTINCT native_id) AS processes,"
    " count(DISTINCT value) AS values"
    " FROM processes CROSS JOIN unnest(processes.classifications) AS stored(value)"
    " GROUP BY scheme ORDER BY scheme"
)
_CLASSIFICATION_VALUES = (
    "SELECT value, count(DISTINCT native_id) FROM processes"
    " CROSS JOIN unnest(processes.classifications) AS stored(value)"
    f" WHERE {_SCHEME} = ? GROUP BY value ORDER BY value"
)
_WEIGHTING_SETS = 'SELECT "row", name, unit FROM weighting_sets WHERE family = ? ORDER BY "row"'
_WEIGHTING_FACTORS = (
    'SELECT f."row", f.key, f.normalisation, f.weighting FROM weighting_factors AS f'
    ' JOIN weighting_sets AS s ON s."row" = f."row"'
    ' WHERE s.family = ? ORDER BY f."row", f.position'
)
_FACTOR_FLOWS = (
    "SELECT code, name, compartment, sub_compartment, unit FROM flows"
    " WHERE code IN (SELECT unnest(?::VARCHAR[]))"
)
_FLOWS = (
    "SELECT code, name, compartment, sub_compartment, unit, flow_type, cas, cas_as_published,"
    " synonyms FROM flows WHERE code IN (SELECT unnest(?::VARCHAR[]))"
)
_FLOW = (
    "SELECT code, name, compartment, sub_compartment, unit, flow_type, cas, cas_as_published,"
    " synonyms FROM flows WHERE code = ?"
)


def _flow(database: str, row: tuple) -> ElementaryFlow:
    """One row of the flows table as the flow it describes in the database given."""
    code, name, compartment, sub_compartment, unit, flow_type, cas, published, synonyms = row
    return ElementaryFlow(
        ref=ElementaryFlowRef(database=database, id=code),
        name=name,
        compartment=cast(CompartmentName, compartment),
        sub_compartment=sub_compartment,
        unit=unit,
        flow_type=flow_type,
        cas_number=cas,
        cas_as_published=published,
        synonyms=list(synonyms),
    )


def _input(
    database: str, elementary_flows: str, kind: ExchangeType, target: str | None
) -> BackgroundRef | ElementaryFlowRef | None:
    """An exchange's input: a background dataset, an elementary flow, and none for a cut-off."""
    if target is None:
        return None
    if kind == "product":
        return BackgroundRef(database=database, id=target)
    return ElementaryFlowRef(database=elementary_flows, id=target)


class NativeInventory:
    """Read-only background data from the catalogs of the databases the store serves."""

    def __init__(self, store: NativeStore) -> None:
        self.store = store

    async def list_databases(self) -> list[Database]:
        return self.store.databases()

    async def get_database(self, name: str) -> Database:
        return self.store.registered(self.store.technosphere_of(name)).database

    async def get_process(self, ref: BackgroundRef, exchanges: bool = False) -> BackgroundProcess:
        elementary_flows = self.store.elementary_flows_of(ref.database)

        def read() -> BackgroundProcess:
            catalog = self.store.catalog(ref.database)
            found = catalog.execute(
                "SELECT name, reference_product, location, unit, classifications, comment, url"
                " FROM processes WHERE native_id = ?",
                [ref.id],
            ).fetchone()
            if found is None:
                raise NotFound(f"no process {ref.id!r} in {ref.database!r}")
            name, product, location, unit, classifications, comment, url = found
            listed = None
            if exchanges:
                rows = catalog.execute(
                    'SELECT type, side, "reference", input, flow, supplier, supplier_location,'
                    " amount, unit, cut_off FROM exchanges WHERE process = ? ORDER BY position",
                    [ref.id],
                ).fetchall()
                listed = [
                    BackgroundExchange(
                        input=_input(ref.database, elementary_flows, kind, target),
                        type=kind,
                        side=side,
                        reference=reference,
                        flow=flow,
                        supplier=supplier,
                        supplier_location=supplier_location,
                        amount=amount,
                        unit=unit,
                        cut_off=cut_off,
                    )
                    for (
                        kind,
                        side,
                        reference,
                        target,
                        flow,
                        supplier,
                        supplier_location,
                        amount,
                        unit,
                        cut_off,
                    ) in rows
                ]
            return BackgroundProcess(
                ref=ref,
                name=name,
                reference_product=product,
                location=location,
                unit=unit,
                classifications=list(classifications),
                comment=comment,
                url=url,
                exchanges=listed,
            )

        return await self.store.run(ref.database, read)

    async def missing(
        self, refs: Sequence[BackgroundRef | ElementaryFlowRef]
    ) -> list[BackgroundRef | ElementaryFlowRef]:
        """The references among these that their database does not hold, in the order given;
        NotFound for a database the store does not serve."""
        held: dict[tuple[str, str], set[str]] = {}
        for ref in refs:
            key = (ref.kind, ref.database)
            if key not in held:
                held[key] = await self._codes(ref)
        return [ref for ref in refs if ref.id not in held[(ref.kind, ref.database)]]

    async def treatments(self, refs: Sequence[BackgroundRef]) -> list[BackgroundRef]:
        """The processes among these that are treatments, their production negative in the
        compiled background, in the order given; NotFound for a database the store does not
        serve."""
        treating: dict[str, frozenset[str]] = {}
        for ref in refs:
            if ref.database not in treating:
                treating[ref.database] = await self._treating(ref.database)
        return [ref for ref in refs if ref.id in treating[ref.database]]

    async def _treating(self, database: str) -> frozenset[str]:
        owner = self.store.technosphere_of(database)
        return await self.store.run(owner, lambda: self.store.background(owner).treating())

    async def _codes(self, ref: BackgroundRef | ElementaryFlowRef) -> set[str]:
        if isinstance(ref, BackgroundRef):
            owner, query = (
                self.store.technosphere_of(ref.database),
                "SELECT native_id FROM processes",
            )
        else:
            owner, query = (
                self.store.owner_of_elementary_flows(ref.database),
                "SELECT code FROM flows",
            )
        rows = await self.store.run(
            owner, lambda: self.store.catalog(owner).execute(query).fetchall()
        )
        return {row[0] for row in rows}

    async def get_elementary_flow(self, ref: ElementaryFlowRef) -> ElementaryFlow:
        owner = self.store.owner_of_elementary_flows(ref.database)

        def read() -> ElementaryFlow:
            found = self.store.catalog(owner).execute(_FLOW, [ref.id]).fetchone()
            if found is None:
                raise no_flow(ref)
            return _flow(ref.database, found)

        return await self.store.run(owner, read)

    async def get_elementary_flows(self, database: str, ids: Sequence[str]) -> list[ElementaryFlow]:
        """One flow per id the database holds, in the order given; an id it does not hold is left
        out, and NotFound for a name no served database uses for its flows."""
        owner = self.store.owner_of_elementary_flows(database)

        def read() -> list[ElementaryFlow]:
            rows = self.store.catalog(owner).execute(_FLOWS, [list(ids)]).fetchall()
            held = {row[0]: row for row in rows}
            return [_flow(database, held[code]) for code in ids if code in held]

        return await self.store.run(owner, read)

    async def list_methods(self, database: str, impact_method: str | None = None) -> list[Method]:
        def read() -> list[Method]:
            rows = self.store.catalog(database).execute("SELECT key, unit FROM methods").fetchall()
            return sorted(
                (Method.of(tuple(key), unit) for key, unit in rows), key=lambda m: m.tuple
            )

        methods = await self.store.run(database, read)
        return [m for m in methods if impact_method is None or m.impact_method == impact_method]

    async def resolve_method(self, database: str, reference: str) -> Method:
        return method_named(await self.list_methods(database), database, reference)

    async def weighting_sets(self, database: str, impact_method: str) -> list[WeightingSet]:
        """Every normalisation and weighting set of a method family, in the bundle's order, each
        factor naming its category by the method's id and a set the bundle gives no factor an empty
        list; NotFound when the database holds no method of that family."""
        listed = await self.list_methods(database, impact_method)
        if not listed:
            raise NotFound(f"no impact method {impact_method!r} in {database!r}")
        ids = {method.tuple: method.id for method in listed}

        def read() -> list[WeightingSet]:
            catalog = self.store.catalog(database)
            found = catalog.execute(_WEIGHTING_SETS, [impact_method]).fetchall()
            sets = {
                row: WeightingSet(impact_method=impact_method, name=name, unit=unit, factors=[])
                for row, name, unit in found
            }
            factors = catalog.execute(_WEIGHTING_FACTORS, [impact_method]).fetchall()
            for row, key, normalisation, weighting in factors:
                method_id = ids.get(tuple(key))
                if method_id is None:
                    raise NotFound(f"no method {tuple(key)!r} in {database!r}")
                sets[row].factors.append(
                    WeightingFactor(
                        method_id=method_id, normalisation=normalisation, weighting=weighting
                    )
                )
            return [sets[row] for row, _name, _unit in found]

        return await self.store.run(database, read)

    async def _values(self, database: str, statement: str) -> list[str]:
        rows = await self.store.run(
            database, lambda: self.store.catalog(database).execute(statement).fetchall()
        )
        return sorted(value for (value,) in rows)

    async def list_units(self, database: str) -> list[str]:
        return await self._values(database, _UNITS)

    async def list_locations(self, database: str) -> list[Location]:
        rows = await self.store.run(
            database, lambda: self.store.catalog(database).execute(_LOCATIONS).fetchall()
        )
        return [Location(code=code, name=name) for code, name in rows]

    async def summarize(self, database: str) -> DatabaseSummary:
        def read() -> tuple[int, int, int, int]:
            catalog = self.store.catalog(database)
            [(processes,)] = catalog.execute("SELECT count(*) FROM processes").fetchall()
            [(flows,)] = catalog.execute("SELECT count(*) FROM flows").fetchall()
            [(methods,)] = catalog.execute("SELECT count(*) FROM methods").fetchall()
            [(locations,)] = catalog.execute("SELECT count(*) FROM locations").fetchall()
            return processes, flows, methods, locations

        processes, elementary_flows, indicators, locations = await self.store.run(database, read)
        return DatabaseSummary(
            processes=processes,
            elementary_flows=elementary_flows,
            indicators=indicators,
            units=len(await self.list_units(database)),
            locations=locations,
        )

    async def list_classifications(self, database: str) -> list[ClassificationScheme]:
        rows = await self.store.run(
            database, lambda: self.store.catalog(database).execute(_CLASSIFICATIONS).fetchall()
        )
        return [
            ClassificationScheme(scheme=scheme, processes=processes, values=values)
            for scheme, processes, values in rows
        ]

    async def classification_values(self, database: str, scheme: str) -> list[ClassificationValue]:
        rows = await self.store.run(
            database,
            lambda: (
                self.store.catalog(database).execute(_CLASSIFICATION_VALUES, [scheme]).fetchall()
            ),
        )
        if not rows:
            raise NotFound(f"no classification scheme {scheme!r} in {database!r}")
        return [ClassificationValue(value=value, processes=processes) for value, processes in rows]

    async def list_compartments(self, database: str) -> list[Compartment]:
        rows = await self.store.run(
            database,
            lambda: (
                self.store.catalog(database)
                .execute("SELECT compartment, sub_compartment FROM flows")
                .fetchall()
            ),
        )
        return Compartment.tally(
            (cast(CompartmentName, compartment), sub) for compartment, sub in rows
        )

    async def factors(
        self,
        database: str,
        method_id: str,
        query: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[Factor]:
        owner = self.store.technosphere_of(database)
        elementary_flows = self.store.elementary_flows_of(owner)

        def read() -> list[Factor]:
            factors = self.store.background(owner).factors_of(method_id)
            rows = (
                self.store.catalog(owner)
                .execute(_FACTOR_FLOWS, [[code for code, _ in factors]])
                .fetchall()
            )
            described = {
                code: (name, compartment, sub, unit) for code, name, compartment, sub, unit in rows
            }
            missing = [code for code, _ in factors if code not in described]
            if missing:
                raise no_flow(ElementaryFlowRef(database=elementary_flows, id=missing[0]))
            return [
                Factor(
                    flow=ElementaryFlowRef(database=elementary_flows, id=code),
                    name=described[code][0],
                    compartment=cast(CompartmentName, described[code][1]),
                    sub_compartment=described[code][2],
                    unit=described[code][3],
                    factor=factor,
                )
                for code, factor in factors
            ]

        return factor_page(await self.store.run(owner, read), query, limit, cursor)
