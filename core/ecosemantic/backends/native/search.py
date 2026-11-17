"""The search port over the catalogs: every term of a query matched as a phrase, and the rows that
match all of them ranked by SQLite FTS5's BM25, computed in SQL over the catalog's terms."""

from __future__ import annotations

from collections.abc import Sequence

from ecosemantic.backends.native.catalog import Kind
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.search import Phrase, browsed, phrases, spellings
from ecosemantic.ports.types import ElementaryFlowHit, FlowType, Page, ProcessHit, page_start

WEIGHTS: dict[Kind, list[float]] = {
    "process": [5.0, 3.0],
    "flow": [1.0, 1.0, 1.0, 1.0],
    "method": [1.0],
}
_TABLES: dict[Kind, str] = {"process": "processes", "flow": "flows", "method": "methods"}


def _phrase(at: int, phrase: Phrase, parameters: dict[str, object]) -> str:
    """The rows a phrase matches, each with the weighted count of its matches."""
    joins = "".join(
        f" JOIN terms t{k} ON t{k}.kind = t0.kind AND t{k}.row = t0.row"
        f" AND t{k}.field = t0.field AND t{k}.position = t0.position + {k}"
        for k in range(1, len(phrase.tokens))
    )
    matches = []
    for k, token in enumerate(phrase.tokens):
        last = k == len(phrase.tokens) - 1
        if k == 0 and not (phrase.prefix and last):
            parameters[f"p{at}t{k}"] = list(spellings(phrase))
            matches.append(f"list_contains($p{at}t{k}, t{k}.term)")
            continue
        parameters[f"p{at}t{k}"] = token
        matches.append(
            f"starts_with(t{k}.term, $p{at}t{k})"
            if phrase.prefix and last
            else f"t{k}.term = $p{at}t{k}"
        )
    return (
        f"p{at} AS (SELECT t0.row AS row, sum(list_extract($weights, t0.field + 1)) AS f"
        f" FROM terms t0{joins} WHERE t0.kind = $kind AND {' AND '.join(matches)}"
        " GROUP BY t0.row),"
        f" i{at} AS (SELECT CASE WHEN x > 0 THEN x ELSE 1e-6::DOUBLE END AS idf FROM"
        " (SELECT ln((stats.n - hits.n + 0.5::DOUBLE) / (hits.n + 0.5::DOUBLE)) AS x"
        f" FROM stats, (SELECT count(*)::DOUBLE AS n FROM p{at}) AS hits))"
    )


def ranked(
    kind: Kind,
    found: list[Phrase],
    columns: str,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    limit: int,
    offset: int,
) -> tuple[str, dict[str, object]]:
    """The statement and its parameters that rank the rows of a kind matching every phrase, best
    first and then by row, filtered and paged, one row past the page."""
    parameters: dict[str, object] = {
        "kind": kind,
        "weights": WEIGHTS[kind],
        "limit": limit + 1,
        "offset": offset,
    }
    ctes = [
        "stats AS (SELECT count(*)::DOUBLE AS n, sum(tokens)::DOUBLE / count(*) AS avgdl"
        " FROM lengths WHERE kind = $kind)"
    ]
    ctes += [_phrase(at, phrase, parameters) for at, phrase in enumerate(found)]
    joined = "".join(f" JOIN p{at} ON p{at}.row = p0.row" for at in range(1, len(found)))
    idfs = "".join(f", i{at}" for at in range(len(found)))
    score = " + ".join(
        f"i{at}.idf * (p{at}.f * (1.2::DOUBLE + 1.0::DOUBLE))"
        f" / (p{at}.f + 1.2::DOUBLE * (1.0::DOUBLE - 0.75::DOUBLE"
        " + 0.75::DOUBLE * lengths.tokens / stats.avgdl))"
        for at in range(len(found))
    )
    where = _filter(filters, classifications, parameters)
    statement = (
        f"WITH {', '.join(ctes)}, scored AS (SELECT p0.row AS row, {score} AS score FROM p0{joined}"
        " JOIN lengths ON lengths.kind = $kind AND lengths.row = p0.row, stats"
        f"{idfs})"
        f" SELECT {columns}, scored.score FROM scored JOIN {_TABLES[kind]} AS entity"
        f" ON entity.row = scored.row WHERE TRUE{where}"
        " ORDER BY scored.score DESC, entity.row LIMIT $limit OFFSET $offset"
    )
    return statement, parameters


def _given(filters: dict[str, str | None]) -> dict[str, str]:
    """The filters that hold a value."""
    return {column: value for column, value in filters.items() if value is not None}


def _filter(
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    parameters: dict[str, object],
) -> str:
    """The WHERE clause a statement narrows a table's rows by, with each value bound in
    parameters: one equality a column filter names, and for classifications, any of a process's
    stored values."""
    where = ""
    for column, value in filters.items():
        parameters[f"filter_{column}"] = value
        where += f" AND entity.{column} = $filter_{column}"
    if classifications is not None:
        parameters["filter_classifications"] = list(classifications)
        where += " AND list_has_any(entity.classifications, $filter_classifications)"
    return where


def _browsing(
    kind: Kind,
    columns: str,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    order: str,
    limit: int,
    offset: int,
) -> tuple[str, dict[str, object]]:
    """The statement and its parameters that list the rows of a kind a filter matches, in the order
    given, paged and one row past the page, each carrying a relevance of 0."""
    parameters: dict[str, object] = {"limit": limit + 1, "offset": offset}
    where = _filter(filters, classifications, parameters)
    statement = (
        f"SELECT {columns}, 0.0::DOUBLE FROM {_TABLES[kind]} AS entity WHERE TRUE{where}"
        f" ORDER BY {order} LIMIT $limit OFFSET $offset"
    )
    return statement, parameters


class NativeSearch:
    """Text search over the catalogs of the databases the store serves."""

    def __init__(self, store: NativeStore) -> None:
        self.store = store

    async def _rows(
        self,
        database: str,
        kind: Kind,
        found: list[Phrase],
        columns: str,
        filters: dict[str, str | None],
        classifications: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple], bool]:
        """The page's rows of a kind, one row past it and whether there is more, ranked best first
        among the rows matching every phrase and the filters."""
        if not found:
            return [], False
        statement, parameters = ranked(
            kind, found, columns, _given(filters), classifications, limit, offset
        )
        return await self._fetch(database, statement, parameters, limit)

    async def _browsed(
        self,
        database: str,
        kind: Kind,
        columns: str,
        filters: dict[str, str | None],
        classifications: Sequence[str] | None,
        order: str,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple], bool]:
        """The page's rows of a kind a browsing filter matches, one row past it and whether there is
        more, in the order given."""
        statement, parameters = _browsing(
            kind, columns, _given(filters), classifications, order, limit, offset
        )
        return await self._fetch(database, statement, parameters, limit)

    async def _fetch(
        self, database: str, statement: str, parameters: dict[str, object], limit: int
    ) -> tuple[list[tuple], bool]:
        """The statement's rows, cut to the page, and whether it answered one past it."""
        rows = await self.store.run(
            database,
            lambda: self.store.catalog(database).execute(statement, parameters).fetchall(),
        )
        return rows[:limit], len(rows) > limit

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
        offset = page_start(cursor, limit)
        columns = (
            "entity.native_id, entity.name, entity.reference_product, entity.location, entity.unit"
        )
        filters = {"location": location, "unit": unit}
        found = browsed(query, classifications is not None)
        if found is None:
            rows, more = await self._browsed(
                database,
                "process",
                columns,
                filters,
                classifications,
                "entity.name, entity.location, entity.row",
                limit,
                offset,
            )
        else:
            rows, more = await self._rows(
                database, "process", found, columns, filters, classifications, limit, offset
            )
        items = [
            ProcessHit(
                ref=BackgroundRef(database=database, id=native_id),
                name=name,
                reference_product=product,
                location=place,
                unit=unit_of,
                relevance=score,
            )
            for native_id, name, product, place, unit_of, score in rows
        ]
        return Page.at_offset(items, more, offset, limit)

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
        offset = page_start(cursor, limit)
        elementary_flows = self.store.elementary_flows_of(database)
        columns = (
            "entity.code, entity.name, entity.compartment, entity.sub_compartment, entity.unit,"
            " entity.flow_type, entity.cas"
        )
        filters = {
            "compartment": compartment,
            "sub_compartment": sub_compartment,
            "flow_type": flow_type,
            "unit": unit,
        }
        found = browsed(query, compartment is not None or sub_compartment is not None)
        if found is None:
            rows, more = await self._browsed(
                database,
                "flow",
                columns,
                filters,
                None,
                "entity.name, entity.compartment, entity.row",
                limit,
                offset,
            )
        else:
            rows, more = await self._rows(
                database, "flow", found, columns, filters, None, limit, offset
            )
        items = [
            ElementaryFlowHit(
                ref=ElementaryFlowRef(database=elementary_flows, id=code),
                name=name,
                compartment=placed,
                sub_compartment=sub,
                unit=unit_of,
                flow_type=kind,
                cas_number=cas,
            )
            for code, name, placed, sub, unit_of, kind, cas, _ in rows
        ]
        return Page.at_offset(items, more, offset, limit)

    async def methods(
        self, database: str, query: str, limit: int = 20, cursor: str | None = None
    ) -> Page[Method]:
        offset = page_start(cursor, limit)
        rows, more = await self._rows(
            database, "method", phrases(query), "entity.key, entity.unit", {}, None, limit, offset
        )
        items = [Method.of(tuple(key), unit) for key, unit, _ in rows]
        return Page.at_offset(items, more, offset, limit)
