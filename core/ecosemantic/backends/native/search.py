"""The search port over the catalogs: every term of a query matched as a phrase, and the rows that
match all of them ranked by SQLite FTS5's BM25, computed in SQL over the catalog's terms."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ecosemantic.backends.native.catalog import Kind
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.search import Phrase, browsed, phrases, spellings
from ecosemantic.ports.types import (
    CompartmentName,
    ElementaryFlowHit,
    FlowType,
    ListingOrder,
    Page,
    ProcessHit,
    page_holding,
    page_start,
)

WEIGHTS: dict[Kind, list[float]] = {
    "process": [5.0, 3.0],
    "flow": [1.0, 1.0, 1.0, 1.0],
    "method": [1.0],
}
_TABLES: dict[Kind, str] = {"process": "processes", "flow": "flows", "method": "methods"}
_IDS: dict[Kind, str] = {"process": "native_id", "flow": "code", "method": "row"}
_SCORED_ORDER = "scored.score DESC, entity.row"


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


def _scoring(kind: Kind, found: list[Phrase], parameters: dict[str, object]) -> str:
    """The opening CTEs of a statement that ranks: every phrase's matches, and the rows matching
    all of them, each with the score it is ranked by."""
    parameters["kind"] = kind
    parameters["weights"] = WEIGHTS[kind]
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
    return (
        f"WITH {', '.join(ctes)}, scored AS (SELECT p0.row AS row, {score} AS score FROM p0{joined}"
        " JOIN lengths ON lengths.kind = $kind AND lengths.row = p0.row, stats"
        f"{idfs})"
    )


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


def _listed(
    kind: Kind,
    found: list[Phrase] | None,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    order: str,
    parameters: dict[str, object],
) -> str:
    """The statement's opening CTE: the rows a query and the filters match, each with the score it
    carries and its 0-based position in the listing's order. A query of no phrase matches every
    row, each with a score of 0."""
    where = _filter(filters, classifications, parameters)
    if found is None:
        opening = "WITH"
        source = f"{_TABLES[kind]} AS entity"
        score = "0.0::DOUBLE"
    else:
        opening = f"{_scoring(kind, found, parameters)},"
        source = f"scored JOIN {_TABLES[kind]} AS entity ON entity.row = scored.row"
        score = "scored.score"
    return (
        f"{opening} listed AS (SELECT entity.row AS row, entity.{_IDS[kind]} AS id,"
        f" {score} AS score, row_number() OVER (ORDER BY {order}) - 1 AS position"
        f" FROM {source} WHERE TRUE{where})"
    )


def _rows(
    kind: Kind,
    found: list[Phrase] | None,
    columns: str,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    order: str,
    limit: int,
    offset: int,
) -> tuple[str, dict[str, object]]:
    """The statement and its parameters that answer one page of a listing in the order given, one
    row past the page."""
    parameters: dict[str, object] = {"limit": limit + 1, "offset": offset}
    listed = _listed(kind, found, filters, classifications, order, parameters)
    return (
        f"{listed} SELECT {columns}, listed.score FROM listed"
        f" JOIN {_TABLES[kind]} AS entity ON entity.row = listed.row"
        " ORDER BY listed.position LIMIT $limit OFFSET $offset",
        parameters,
    )


def _count(
    kind: Kind,
    found: list[Phrase] | None,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    order: str,
) -> tuple[str, dict[str, object]]:
    """The statement and its parameters that count the rows a query and the filters match, the
    order only numbering the rows it counts."""
    parameters: dict[str, object] = {}
    listed = _listed(kind, found, filters, classifications, order, parameters)
    return f"{listed} SELECT count(*) FROM listed", parameters


def _position(
    kind: Kind,
    found: list[Phrase] | None,
    filters: dict[str, str],
    classifications: Sequence[str] | None,
    order: str,
    item: str,
) -> tuple[str, dict[str, object]]:
    """The statement and its parameters that answer the 0-based position, the one `page_holding`
    takes, of the row an id names among the rows a query and the filters match in the order given,
    and no row when the listing does not hold it."""
    parameters: dict[str, object] = {"item": item}
    listed = _listed(kind, found, filters, classifications, order, parameters)
    return f"{listed} SELECT position FROM listed WHERE id = $item", parameters


@dataclass(frozen=True)
class _Listing:
    """One of a kind's listings: the columns it answers, the values its filters take, and the
    order it falls in when no query ranks it."""

    kind: Kind
    columns: str
    filters: dict[str, str | None]
    browse_order: str
    classifications: Sequence[str] | None = None


@dataclass(frozen=True)
class _Answered:
    """One page of a listing: its rows, whether more follow it, the offset it starts at and the
    number of rows the listing holds."""

    rows: list[tuple]
    has_more: bool
    offset: int
    total: int


class NativeSearch:
    """Text search over the catalogs of the databases the store serves."""

    def __init__(self, store: NativeStore) -> None:
        self.store = store

    async def _fetch(
        self, database: str, statement: str, parameters: dict[str, object]
    ) -> list[tuple]:
        """The rows the statement answers."""
        return await self.store.run(
            database,
            lambda: self.store.catalog(database).execute(statement, parameters).fetchall(),
        )

    async def _page(
        self,
        database: str,
        listing: _Listing,
        found: list[Phrase] | None,
        order: ListingOrder,
        limit: int,
        cursor: str | None,
        item: str | None,
    ) -> _Answered:
        """One page of a listing, whether more rows follow it, and how many rows the query and the
        filters match; without a cursor, the page that holds the row an item id names, and the
        first page when the listing does not hold it. A query whose terms carry no token matches
        nothing."""
        offset = page_start(cursor, limit)
        if found == []:
            return _Answered(rows=[], has_more=False, offset=offset, total=0)
        by = listing.browse_order if found is None or order == "name" else _SCORED_ORDER
        filters = _given(listing.filters)
        if item is not None and cursor is None:
            statement, parameters = _position(
                kind=listing.kind,
                found=found,
                filters=filters,
                classifications=listing.classifications,
                order=by,
                item=item,
            )
            held = await self._fetch(database, statement, parameters)
            offset = page_holding(int(held[0][0]) if held else None, limit)
        statement, parameters = _rows(
            kind=listing.kind,
            found=found,
            columns=listing.columns,
            filters=filters,
            classifications=listing.classifications,
            order=by,
            limit=limit,
            offset=offset,
        )
        rows = await self._fetch(database, statement, parameters)
        statement, parameters = _count(
            kind=listing.kind,
            found=found,
            filters=filters,
            classifications=listing.classifications,
            order=by,
        )
        counted = await self._fetch(database, statement, parameters)
        return _Answered(
            rows=rows[:limit],
            has_more=len(rows) > limit,
            offset=offset,
            total=int(counted[0][0]),
        )

    async def processes(
        self,
        database: str,
        query: str,
        location: str | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        classifications: Sequence[str] | None = None,
        order: ListingOrder = "relevance",
        item: str | None = None,
    ) -> Page[ProcessHit]:
        answered = await self._page(
            database=database,
            listing=_Listing(
                kind="process",
                columns=(
                    "entity.native_id, entity.name, entity.reference_product, entity.location,"
                    " entity.unit"
                ),
                filters={"location": location, "unit": unit},
                browse_order="entity.name, entity.location, entity.row",
                classifications=classifications,
            ),
            found=browsed(query, classifications is not None),
            order=order,
            limit=limit,
            cursor=cursor,
            item=item,
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
            for native_id, name, product, place, unit_of, score in answered.rows
        ]
        return Page.at_offset(
            items=items,
            has_more=answered.has_more,
            offset=answered.offset,
            limit=limit,
            total=answered.total,
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
        order: ListingOrder = "relevance",
        item: str | None = None,
    ) -> Page[ElementaryFlowHit]:
        elementary_flows = self.store.elementary_flows_of(database)
        answered = await self._page(
            database=database,
            listing=_Listing(
                kind="flow",
                columns=(
                    "entity.code, entity.name, entity.compartment, entity.sub_compartment,"
                    " entity.unit, entity.flow_type, entity.cas, entity.cas_as_published"
                ),
                filters={
                    "compartment": compartment,
                    "sub_compartment": sub_compartment,
                    "flow_type": flow_type,
                    "unit": unit,
                },
                browse_order="entity.name, entity.compartment, entity.row",
            ),
            found=browsed(query, compartment is not None or sub_compartment is not None),
            order=order,
            limit=limit,
            cursor=cursor,
            item=item,
        )
        items = [
            ElementaryFlowHit(
                ref=ElementaryFlowRef(database=elementary_flows, id=code),
                name=name,
                compartment=cast(CompartmentName, placed),
                sub_compartment=sub,
                unit=unit_of,
                flow_type=kind,
                cas_number=cas,
                cas_as_published=published,
            )
            for code, name, placed, sub, unit_of, kind, cas, published, _ in answered.rows
        ]
        return Page.at_offset(
            items=items,
            has_more=answered.has_more,
            offset=answered.offset,
            limit=limit,
            total=answered.total,
        )

    async def methods(
        self, database: str, query: str, limit: int = 20, cursor: str | None = None
    ) -> Page[Method]:
        answered = await self._page(
            database=database,
            listing=_Listing(
                kind="method",
                columns="entity.key, entity.unit",
                filters={},
                browse_order="entity.row",
            ),
            found=phrases(query),
            order="relevance",
            limit=limit,
            cursor=cursor,
            item=None,
        )
        items = [Method.of(tuple(key), unit) for key, unit, _ in answered.rows]
        return Page.at_offset(
            items=items,
            has_more=answered.has_more,
            offset=answered.offset,
            limit=limit,
            total=answered.total,
        )
