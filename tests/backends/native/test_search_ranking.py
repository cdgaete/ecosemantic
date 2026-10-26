"""The catalog's search held to SQLite FTS5 on the same rows: the hits of every query, in order,
and their scores. FTS5 is the referee; its schema is the core's index of processes, flows and
methods."""

import json
import sqlite3
from collections.abc import Iterator

import pytest

from ecosemantic.backends.native.catalog import catalog_rows, write_catalog
from ecosemantic.backends.native.search import NativeSearch
from ecosemantic.backends.native.store import FORMAT, Entry, NativeStore
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import Database
from ecosemantic.package.background import Import, ImportedMethod
from tests.fixture_data import PROCESSES

NAME = "ranking"
# a catalog alone: no background is compiled, so its fingerprint names none
DATABASE = Database(
    name=NAME,
    elementary_flows=f"{NAME}-biosphere",
    scheme="olca",
    version="1",
    system_model="unit process",
    fingerprint="0" * 64,
)
EXTRA = [
    ("PM2.5 emission, low-voltage", "particulate matter", "CH", "kilogram"),
    ("Cátodo de cobre", "copper cathode", "CL", "kilogram"),
    ("market for electricity, low voltage", "electricity, low voltage", "CH", "kilowatt hour"),
    ("market for electricity, high voltage", "electricity, high voltage", "CH", "kilowatt hour"),
    (
        "electricity production, hydro, run-of-river",
        "electricity, high voltage",
        "NO",
        "kilowatt hour",
    ),
    (
        "heat, district or industrial, natural gas",
        "heat, district or industrial",
        "CH",
        "megajoule",
    ),
    ("steel steel steel rolling", "steel, low-alloyed, hot rolled", "GLO", "kilogram"),
    ("treatment of waste wood, untreated, municipal incineration", "waste wood", "CH", "kilogram"),
    ("voltage transformation, low loss", "electricity, medium voltage", "CH", "kilowatt hour"),
]
PROCESS_ROWS = [
    (name, product, "GLO", unit) for name, product, unit, _, _ in PROCESSES.values()
] + EXTRA
FLOW_ROWS = [
    ("Carbon dioxide, fossil", ("air",), "124-38-9"),
    ("Carbon dioxide, fossil", ("air", "urban air close to ground"), "124-38-9"),
    ("Methane, fossil", ("air", "non-urban air or from high stacks"), "74-82-8"),
    ("Water, river", ("Resource", "in water"), None),
    ("Particulate Matter, < 2.5 um", ("air", "urban air close to ground"), None),
    ("Copper, Cu 0.38%, in mixed ore", ("Resource", "in ground"), "7440-50-8"),
    ("Sulfur dioxide", ("air",), "7446-09-5"),
]
METHOD_KEYS = [
    (NAME, "IPCC 2021", "climate change: fossil > global warming potential (GWP100)"),
    (NAME, "IPCC 2021", "climate change: biogenic > global warming potential (GWP100)"),
    (NAME, "EF v3.1", "climate change > global warming potential (GWP100)"),
    (NAME, "EF v3.1", "water use > user deprivation potential"),
    (NAME, "ReCiPe 2016 v1.03, midpoint (H)", "particulate matter formation > PMFP"),
]
PROCESS_QUERIES = [
    "steel",
    "production",
    "electricity voltage",
    "low-voltage",
    "pm2.5",
    "pm2*",
    "cat*",
    "catodo",
    "elec* low",
    "market for electricity",
    "heat natural gas",
    "steel production",
    "steel -",
    '"low voltage"',
    "voltage high",
    "el*",
    "wood*",
]
FLOW_QUERIES = ["carbon", "fossil air", "urban", "124-38-9", "resource", "copper", "2.5", "w*"]
METHOD_QUERIES = ["climate", "global warming", "gwp100", "EF", "water", "mid*", "climate fossil"]


def fts5_query(text: str) -> str:
    terms = [t.replace('"', "") for t in text.split()]
    terms = [t for t in terms if t.strip("*")]
    return " ".join(f'"{t[:-1]}"*' if t.endswith("*") else f'"{t}"' for t in terms)


def imported() -> Import:
    datasets = {
        (NAME, f"p{at}"): {
            "name": name,
            "reference product": product,
            "location": location,
            "unit": unit,
            "exchanges": [],
        }
        for at, (name, product, location, unit) in enumerate(PROCESS_ROWS)
    }
    flows = {
        (DATABASE.elementary_flows, f"f{at}"): {
            "name": name,
            "categories": categories,
            "unit": "kilogram",
            "type": "natural resource" if categories[0] == "Resource" else "emission",
            "CAS number": cas,
            "synonyms": [],
        }
        for at, (name, categories, cas) in enumerate(FLOW_ROWS)
    }
    methods = [ImportedMethod(key=key, unit="unit", factors=[]) for key in METHOD_KEYS]
    return Import(
        database=NAME,
        biosphere=DATABASE.elementary_flows,
        datasets=datasets,
        flows=flows,
        methods=methods,
        processes=len(datasets),
    )


@pytest.fixture(scope="module")
def search(tmp_path_factory: pytest.TempPathFactory) -> Iterator[NativeSearch]:
    data = tmp_path_factory.mktemp("ranking")
    target = data / "databases" / NAME
    build = target / "builds" / "fixed"
    build.mkdir(parents=True)
    write_catalog(build / "catalog.duckdb", catalog_rows(imported()))
    entry = Entry(format=FORMAT, database=DATABASE, bundle="0" * 64)
    (build / "entry.json").write_text(entry.model_dump_json(), encoding="utf-8")
    (target / "current").write_text("fixed", encoding="utf-8")
    store = NativeStore(data)
    yield NativeSearch(store)
    store.close()


@pytest.fixture(scope="module")
def fts5() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE processes(id INTEGER PRIMARY KEY, code TEXT, name TEXT, product TEXT,
            location TEXT, unit TEXT);
        CREATE VIRTUAL TABLE processes_fts USING fts5(
            name, product, content='processes', content_rowid='id', tokenize='unicode61');
        CREATE TABLE flows(id INTEGER PRIMARY KEY, code TEXT, name TEXT, compartment TEXT,
            sub_compartment TEXT, cas TEXT);
        CREATE VIRTUAL TABLE flows_fts USING fts5(
            name, compartment, sub_compartment, cas,
            content='flows', content_rowid='id', tokenize='unicode61');
        CREATE TABLE methods(id INTEGER PRIMARY KEY, key TEXT, spec TEXT);
        CREATE VIRTUAL TABLE methods_fts USING fts5(
            spec, content='methods', content_rowid='id', tokenize='unicode61');
        """
    )
    connection.executemany(
        "INSERT INTO processes(code, name, product, location, unit) VALUES (?,?,?,?,?)",
        [(f"p{at}", *row) for at, row in enumerate(PROCESS_ROWS)],
    )
    connection.executemany(
        "INSERT INTO flows(code, name, compartment, sub_compartment, cas) VALUES (?,?,?,?,?)",
        [
            (f"f{at}", name, cats[0], "/".join(cats[1:]) or None, cas)
            for at, (name, cats, cas) in enumerate(FLOW_ROWS)
        ],
    )
    connection.executemany(
        "INSERT INTO methods(key, spec) VALUES (?,?)",
        [(json.dumps(list(key)), Method.of(key, "unit").spec) for key in METHOD_KEYS],
    )
    for table in ("processes", "flows", "methods"):
        connection.execute(f"INSERT INTO {table}_fts({table}_fts) VALUES('rebuild')")
    return connection


def referee(
    fts5: sqlite3.Connection, table: str, column: str, weights: str, query: str, where: str = ""
) -> list[tuple[str, float]]:
    rows = fts5.execute(
        f"SELECT {table}.{column}, bm25({table}_fts{weights})"
        f" FROM {table}_fts JOIN {table} ON {table}.id = {table}_fts.rowid"
        f" WHERE {table}_fts MATCH ?{where}"
        f" ORDER BY bm25({table}_fts{weights}), {table}.id",
        (fts5_query(query),),
    ).fetchall()
    return [(key, -score) for key, score in rows]


def same(ours: list[tuple[str, float]], theirs: list[tuple[str, float]]) -> None:
    assert [key for key, _ in ours] == [key for key, _ in theirs]
    for (_, mine), (_, reference) in zip(ours, theirs, strict=True):
        assert mine == pytest.approx(reference, rel=1e-9)


@pytest.mark.parametrize("query", PROCESS_QUERIES)
async def test_processes_rank_as_fts5_ranks_them(
    search: NativeSearch, fts5: sqlite3.Connection, query: str
) -> None:
    page = await search.processes(NAME, query, limit=50)
    same(
        [(hit.ref.id, hit.relevance) for hit in page.items],
        referee(fts5, "processes", "code", ", 5.0, 3.0", query),
    )


async def test_filters_and_pages_keep_the_fts5_order(
    search: NativeSearch, fts5: sqlite3.Connection
) -> None:
    filtered = await search.processes(NAME, "electricity", location="CH", unit="kilowatt hour")
    where = " AND processes.location = 'CH' AND processes.unit = 'kilowatt hour'"
    same(
        [(hit.ref.id, hit.relevance) for hit in filtered.items],
        referee(fts5, "processes", "code", ", 5.0, 3.0", "electricity", where),
    )
    walked: list[tuple[str, float]] = []
    cursor = None
    while True:
        page = await search.processes(NAME, "production", limit=3, cursor=cursor)
        walked += [(hit.ref.id, hit.relevance) for hit in page.items]
        if not page.has_more:
            break
        cursor = page.next_cursor
    same(walked, referee(fts5, "processes", "code", ", 5.0, 3.0", "production"))


@pytest.mark.parametrize("query", FLOW_QUERIES)
async def test_flows_rank_as_fts5_ranks_them(
    search: NativeSearch, fts5: sqlite3.Connection, query: str
) -> None:
    page = await search.elementary_flows(NAME, query, limit=50)
    same(
        [(hit.ref.id, 0.0) for hit in page.items],
        [(code, 0.0) for code, _ in referee(fts5, "flows", "code", "", query)],
    )


@pytest.mark.parametrize("query", METHOD_QUERIES)
async def test_methods_rank_as_fts5_ranks_them(
    search: NativeSearch, fts5: sqlite3.Connection, query: str
) -> None:
    page = await search.methods(NAME, query, limit=50)
    same(
        [(json.dumps(list(method.tuple)), 0.0) for method in page.items],
        [(key, 0.0) for key, _ in referee(fts5, "methods", "key", "", query)],
    )


async def test_a_query_of_terms_without_tokens_matches_nothing_as_in_fts5(
    search: NativeSearch, fts5: sqlite3.Connection
) -> None:
    assert (await search.processes(NAME, "- —")).items == []
    assert referee(fts5, "processes", "code", ", 5.0, 3.0", "- —") == []
