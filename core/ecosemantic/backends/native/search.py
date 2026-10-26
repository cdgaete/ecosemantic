"""The search port over the catalogs: every term of a query matched as a phrase, and the rows that
match all of them ranked by SQLite FTS5's BM25, computed in SQL over the catalog's terms."""

from __future__ import annotations

from dataclasses import dataclass

from ecosemantic.backends.native.catalog import Kind
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.backends.native.terms import tokens
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.types import ElementaryFlowHit, FlowType, Page, ProcessHit, offset_cursor

WEIGHTS: dict[Kind, list[float]] = {
    "process": [5.0, 3.0],
    "flow": [1.0, 1.0, 1.0, 1.0],
    "method": [1.0],
}
_TABLES: dict[Kind, str] = {"process": "processes", "flow": "flows", "method": "methods"}


@dataclass(frozen=True)
class Phrase:
    """A query term's tokens, matched adjacent and in order within one field; with `prefix`, the
    last token matches any token that begins with it."""

    tokens: tuple[str, ...]
    prefix: bool


def phrases(query: str) -> list[Phrase]:
    """The phrases of a query: terms split on whitespace with double quotes dropped, a term
    ending in `*` a prefix, a term that is only `*` dropped; Invalid when no term is left. A term
    with no token matches nothing and is left out, so a query of such terms only matches
    nothing."""
    terms = [t.replace('"', "") for t in query.split()]
    terms = [t for t in terms if t.strip("*")]
    if not terms:
        raise Invalid("a search needs at least one term")
    found = []
    for term in terms:
        prefix = term.endswith("*")
        words = tokens(term[:-1] if prefix else term)
        if words:
            found.append(Phrase(tokens=tuple(words), prefix=prefix))
    return found


def _phrase(at: int, phrase: Phrase, parameters: dict[str, object]) -> str:
    """The rows a phrase matches, each with the weighted count of its matches."""
    joins = "".join(
        f" JOIN terms t{k} ON t{k}.kind = t0.kind AND t{k}.row = t0.row"
        f" AND t{k}.field = t0.field AND t{k}.position = t0.position + {k}"
        for k in range(1, len(phrase.tokens))
    )
    matches = []
    for k, token in enumerate(phrase.tokens):
        parameters[f"p{at}t{k}"] = token
        last = k == len(phrase.tokens) - 1
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
    where = ""
    for column, value in filters.items():
        parameters[f"filter_{column}"] = value
        where += f" AND entity.{column} = $filter_{column}"
    statement = (
        f"WITH {', '.join(ctes)}, scored AS (SELECT p0.row AS row, {score} AS score FROM p0{joined}"
        " JOIN lengths ON lengths.kind = $kind AND lengths.row = p0.row, stats"
        f"{idfs})"
        f" SELECT {columns}, scored.score FROM scored JOIN {_TABLES[kind]} AS entity"
        f" ON entity.row = scored.row WHERE TRUE{where}"
        " ORDER BY scored.score DESC, entity.row LIMIT $limit OFFSET $offset"
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
        query: str,
        columns: str,
        filters: dict[str, str | None],
        limit: int,
        offset: int,
    ) -> tuple[list[tuple], bool]:
        found = phrases(query)
        if not found:
            return [], False
        given = {column: value for column, value in filters.items() if value is not None}
        statement, parameters = ranked(kind, found, columns, given, limit, offset)
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
    ) -> Page[ProcessHit]:
        offset = offset_cursor(cursor)
        rows, more = await self._rows(
            database,
            "process",
            query,
            "entity.native_id, entity.name, entity.reference_product, entity.location, entity.unit",
            {"location": location, "unit": unit},
            limit,
            offset,
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
        offset = offset_cursor(cursor)
        elementary_flows = self.store.registered(database).database.elementary_flows
        rows, more = await self._rows(
            database,
            "flow",
            query,
            "entity.code, entity.name, entity.compartment, entity.sub_compartment, entity.unit,"
            " entity.flow_type, entity.cas",
            {
                "compartment": compartment,
                "sub_compartment": sub_compartment,
                "flow_type": flow_type,
                "unit": unit,
            },
            limit,
            offset,
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
        offset = offset_cursor(cursor)
        rows, more = await self._rows(
            database, "method", query, "entity.key, entity.unit", {}, limit, offset
        )
        items = [Method.of(tuple(key), unit) for key, unit, _ in rows]
        return Page.at_offset(items, more, offset, limit)
