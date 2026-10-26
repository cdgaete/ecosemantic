import dataclasses
import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from ecosemantic.backends.native import install as install_module
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.engine.background import Background
from ecosemantic.errors import Conflict, Invalid, NotFound, NotSupported
from ecosemantic.package.background import Import, Unlinked, read_background
from ecosemantic.package.base_writer import write_base_bundle
from tests.engine_fixture import NOW, fixture_bundle, fixture_rows
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fixture_bundle(tmp_path_factory.mktemp("sources"))


def imported(bundle: Path, name: str = FIXTURE_DB) -> Import:
    return read_background(bundle, name, foreground=frozenset())


def put(data: Path, bundle: Path, replace: bool = False, name: str = FIXTURE_DB):
    return install(
        data,
        imported(bundle, name),
        bundle,
        version="1",
        system_model="unit process",
        replace=replace,
    )


def test_install_writes_the_entry_the_catalog_and_the_background(
    tmp_path: Path, bundle: Path
) -> None:
    installed = put(tmp_path, bundle)
    target = tmp_path / "databases" / "fixture"
    assert installed.directory == target
    assert (installed.datasets, installed.flows, installed.methods) == (12, 4, 2)
    entry = json.loads((target / "entry.json").read_text())
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    fingerprint = Background.load(target / "background").fingerprint()
    assert entry["format"] == 4 and entry["bundle"] == digest
    assert entry["database"] == {
        "name": FIXTURE_DB,
        "elementary_flows": FIXTURE_BIO,
        "scheme": "olca",
        "version": "1",
        "system_model": "unit process",
        "fingerprint": fingerprint,
    }
    assert installed.database.fingerprint == fingerprint
    assert (tmp_path / "bundles" / f"{digest}.zip").read_bytes() == bundle.read_bytes()
    assert (target / "background" / "background.json").is_file()
    assert sorted(p.name for p in (tmp_path / "databases").iterdir()) == ["fixture"]


def test_the_catalog_holds_the_datasets_exchanges_flows_methods_and_terms(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    catalog = duckdb.connect(tmp_path / "databases" / "fixture" / "catalog.duckdb", read_only=True)
    steel = catalog.execute(
        "SELECT name, reference_product, location, unit, classifications, comment, url"
        " FROM processes WHERE native_id = ?",
        [CODES["steel"]],
    ).fetchone()
    assert steel == ("steel production", "steel", "GLO", "kilogram", [], None, None)
    exchanges = catalog.execute(
        'SELECT position, type, side, "reference", input, flow, supplier, amount, unit, cut_off'
        " FROM exchanges WHERE process = ? ORDER BY position",
        [CODES["steel"]],
    ).fetchall()
    assert exchanges == [
        (0, "product", "output", True, CODES["steel"], "steel", None, 1.0, "kilogram", None),
        (
            1,
            "product",
            "input",
            False,
            CODES["elec"],
            "electricity",
            "electricity production",
            2.0,
            "kilowatt hour",
            None,
        ),
        (
            2,
            "elementary",
            "output",
            False,
            FLOW_IDS["co2"],
            "Carbon dioxide, fossil",
            None,
            0.5,
            "kilogram",
            None,
        ),
        (
            3,
            "elementary",
            "output",
            False,
            FLOW_IDS["ch4"],
            "Methane, fossil",
            None,
            0.01,
            "kilogram",
            None,
        ),
    ]
    water = catalog.execute(
        "SELECT name, compartment, sub_compartment, unit, flow_type FROM flows WHERE code = ?",
        [FLOW_IDS["water_in"]],
    ).fetchone()
    # a bundle files a natural resource under openLCA's "Resource"
    assert water == ("Water, river", "Resource", "in water", "cubic meter", "natural resource")
    assert catalog.execute("SELECT count(*) FROM methods").fetchone() == (2,)
    # a method's id, spec and parts are Method.of(key, unit)'s, never stored beside the key
    columns = [c[0] for c in catalog.execute("DESCRIBE methods").fetchall()]
    assert columns == ["row", "key", "unit"]
    terms = catalog.execute(
        "SELECT field, position, term FROM terms t JOIN processes p ON p.row = t.row"
        " WHERE t.kind = 'process' AND p.native_id = ? ORDER BY field, position",
        [CODES["steel"]],
    ).fetchall()
    assert terms == [(0, 0, "steel"), (0, 1, "production"), (1, 0, "steel")]
    lengths = catalog.execute(
        "SELECT kind, count(*), sum(tokens) FROM lengths GROUP BY kind ORDER BY kind"
    ).fetchall()
    assert [(kind, rows) for kind, rows, _ in lengths] == [
        ("flow", 4),
        ("method", 2),
        ("process", 12),
    ]


def test_a_name_installed_is_refused_without_replace_and_replaced_with_it(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    with pytest.raises(Conflict, match="database 'fixture' is installed in"):
        put(tmp_path, bundle)
    put(tmp_path, bundle, replace=True)
    assert [p.name for p in (tmp_path / "databases").iterdir()] == ["fixture"]
    assert [d.name for d in NativeStore(tmp_path).databases()] == [FIXTURE_DB]


def test_an_entry_of_another_format_is_replaced_by_name(tmp_path: Path, bundle: Path) -> None:
    put(tmp_path, bundle)
    path = tmp_path / "databases" / "fixture" / "entry.json"
    entry = json.loads(path.read_text())
    # format 1 kept the bundle's digest under "archive"
    path.write_text(json.dumps({"format": 1, "database": entry["database"], "archive": "a" * 64}))
    put(tmp_path, bundle, replace=True)
    assert json.loads(path.read_text()) == entry


def renamed(directory: Path) -> Path:
    """The fixture written again with steel's process renamed, beside its own source."""
    rows = fixture_rows()
    datasets = tuple(
        dataclasses.replace(dataset, name="steel production, recycled")
        if dataset.code == CODES["steel"]
        else dataset
        for dataset in rows.datasets
    )
    written = write_base_bundle(
        dataclasses.replace(rows, datasets=datasets),
        scheme="olca",
        name=FIXTURE_DB,
        version="1",
        destination=directory / "renamed.zip",
        now=NOW,
    )
    return written.bundle


def steel_name(store: NativeStore) -> str | None:
    """The name the store's catalog holds for the fixture's steel process."""

    def read() -> str | None:
        catalog = store.catalog(FIXTURE_DB)
        row = catalog.execute(
            "SELECT name FROM processes WHERE native_id = ?", [CODES["steel"]]
        ).fetchone()
        return None if row is None else row[0]

    return store.call(FIXTURE_DB, read)


def test_a_store_serves_a_database_installed_after_it_was_built(
    tmp_path: Path, bundle: Path
) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    assert [database.name for database in running.databases()] == [FIXTURE_DB]
    assert CODES["steel"] in running.native_ids(FIXTURE_DB)
    running.close()


def test_a_second_store_on_the_directory_serves_an_install_it_did_not_carry(
    tmp_path: Path, bundle: Path
) -> None:
    carrying = NativeStore(tmp_path)
    following = NativeStore(tmp_path)
    put(tmp_path, bundle)
    assert carrying.technosphere_of(FIXTURE_DB) == FIXTURE_DB
    assert following.owner_of_elementary_flows(FIXTURE_BIO) == FIXTURE_DB
    assert [database.name for database in carrying.databases()] == [FIXTURE_DB]
    assert [database.name for database in following.databases()] == [FIXTURE_DB]
    assert CODES["steel"] in carrying.native_ids(FIXTURE_DB)
    assert CODES["steel"] in following.native_ids(FIXTURE_DB)
    carrying.close()
    following.close()


def test_a_store_serves_the_new_bundle_of_a_database_installed_again(
    tmp_path: Path, bundle: Path
) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    assert steel_name(running) == "steel production"
    changed = renamed(tmp_path)
    put(tmp_path, changed, replace=True)
    assert [database.name for database in running.databases()] == [FIXTURE_DB]
    assert steel_name(running) == "steel production, recycled"
    digest = hashlib.sha256(changed.read_bytes()).hexdigest()
    assert running.registered(FIXTURE_DB).bundle == digest
    running.close()


def test_a_directory_an_install_is_writing_is_not_served(tmp_path: Path, bundle: Path) -> None:
    running = NativeStore(tmp_path)
    written = put(tmp_path / "other", bundle)
    entry = (written.directory / "entry.json").read_text()
    writing = tmp_path / "databases" / ".fixture.partial-x"
    writing.mkdir(parents=True)
    (writing / "entry.json").write_text(entry)
    assert running.databases() == []
    with pytest.raises(NotFound, match="no database 'fixture' under"):
        running.registered(FIXTURE_DB)
    running.close()


def test_a_directory_another_database_holds_is_refused_even_with_replace(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    with pytest.raises(Conflict, match="holds 'fixture'; 'Fixture' cannot be installed there"):
        put(tmp_path, bundle, replace=True, name="Fixture")


def test_an_unlinked_input_is_refused_before_anything_is_written(
    tmp_path: Path, bundle: Path
) -> None:
    unlinked = Unlinked(
        process="steel production",
        process_id="p",
        flow="coke",
        flow_id="f",
        provider_id=None,
        reason="no provider",
        dataset=CODES["steel"],
        position=1,
        is_input=True,
        amount=0.5,
        unit="kilogram",
    )
    broken = dataclasses.replace(imported(bundle), unlinked=[unlinked])
    with pytest.raises(Invalid):
        install(tmp_path, broken, bundle, version="1", system_model="unit process")
    assert not (tmp_path / "databases").exists()


def test_a_flow_type_the_ports_do_not_name_is_refused_before_anything_is_written(
    tmp_path: Path, bundle: Path
) -> None:
    source = imported(bundle)
    key = next(iter(source.flows))
    flows = dict(source.flows) | {key: source.flows[key] | {"type": "social"}}
    with pytest.raises(NotSupported, match="flow type 'social'"):
        install(
            tmp_path,
            dataclasses.replace(source, flows=flows),
            bundle,
            version="1",
            system_model="unit process",
        )
    assert not (tmp_path / "databases").exists()


def test_a_failure_while_writing_leaves_nothing_behind(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(tmp_path, bundle)

    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(install_module, "write_catalog", broken)
    with pytest.raises(OSError, match="disk full"):
        put(tmp_path, bundle, replace=True)
    assert [p.name for p in (tmp_path / "databases").iterdir()] == ["fixture"]
    assert [d.name for d in NativeStore(tmp_path).databases()] == [FIXTURE_DB]


def test_a_miss_inside_a_query_is_not_found_without_deadlock(tmp_path: Path, bundle: Path) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    with pytest.raises(NotFound, match="no database 'nowhere'"):
        running.call(FIXTURE_DB, lambda: running.technosphere_of("nowhere"))
    running.close()


def test_a_bundle_installed_twice_has_one_fingerprint(tmp_path: Path, bundle: Path) -> None:
    first = put(tmp_path / "first", bundle)
    second = put(tmp_path / "second", bundle)
    assert first.database.fingerprint is not None
    assert first.database.fingerprint == second.database.fingerprint
