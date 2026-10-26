import dataclasses
import hashlib
import json
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from ecosemantic.backends.native import install as install_module
from ecosemantic.backends.native import store as store_module
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.store import NativeStore, install_lock
from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.errors import Conflict, Invalid, NotFound, NotSupported
from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.package.background import Import, Unlinked, read_background
from ecosemantic.package.base_writer import write_base_bundle
from tests.engine_fixture import NOW, fixture_bundle, fixture_rows, served_build
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
    build = served_build(target)
    entry = json.loads((build / "entry.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    fingerprint = Background.load(build / "background").fingerprint()
    assert entry["format"] == 5 and entry["bundle"] == digest
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
    assert (build / "background" / "background.json").is_file()
    assert sorted(p.name for p in (tmp_path / "databases").iterdir()) == ["fixture"]
    assert sorted(p.name for p in (target / "builds").iterdir()) == [build.name]


def test_the_catalog_holds_the_datasets_exchanges_flows_methods_and_terms(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    build = served_build(tmp_path / "databases" / "fixture")
    catalog = duckdb.connect(build / "catalog.duckdb", read_only=True)
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
    build = served_build(tmp_path / "databases" / "fixture")
    path = build / "entry.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    # format 1 kept the bundle's digest under "archive"
    path.write_text(
        json.dumps({"format": 1, "database": entry["database"], "archive": "a" * 64}),
        encoding="utf-8",
    )
    put(tmp_path, bundle, replace=True)
    served = json.loads(
        (served_build(tmp_path / "databases" / "fixture") / "entry.json").read_text(
            encoding="utf-8"
        )
    )
    assert served == entry


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


GWP = Method.of(("fixture", "gwp", "climate change > GWP100"), "kg CO2-Eq")


def score_of(calculation: Calculation) -> float:
    """One kilogram of the fixture's steel, scored for climate change."""
    demand = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)]
    solution = calculation.solve(None, demand)
    return float(calculation.scores(solution, [GWP]).values()[0])


def format_4(tmp_path: Path, bundle: Path) -> tuple[Path, dict]:
    """The fixture downgraded to a format-4 directory; its target and its entry."""
    put(tmp_path, bundle)
    target = tmp_path / "databases" / "fixture"
    build = served_build(target)
    entry = json.loads((build / "entry.json").read_text(encoding="utf-8"))
    shutil.move(str(build / "background"), str(target / "background"))
    shutil.move(str(build / "catalog.duckdb"), str(target / "catalog.duckdb"))
    (target / "entry.json").write_text(
        json.dumps({"format": 4, "database": entry["database"], "bundle": entry["bundle"]}),
        encoding="utf-8",
    )
    (target / "current").unlink()
    shutil.rmtree(target / "builds")
    return target, entry


def steel_name(store: NativeStore) -> str | None:
    """The name the store's catalog holds for the fixture's steel process."""

    def read() -> str | None:
        catalog = store.catalog(FIXTURE_DB)
        row = catalog.execute(
            "SELECT name FROM processes WHERE native_id = ?", [CODES["steel"]]
        ).fetchone()
        return None if row is None else row[0]

    return store.call(FIXTURE_DB, read)


def _windows_rmtree(held: str) -> Callable[[Path], None]:
    """An rmtree with Windows semantics: children in name order, raising on the held file."""

    def rmtree(path: object, *_: object, **__: object) -> None:
        for child in sorted(Path(path).iterdir(), key=lambda p: p.name):
            if child.is_dir():
                rmtree(child)
            else:
                if child.name == held:
                    error = PermissionError(f"held {child.name}")
                    error.winerror = 5
                    raise error
                child.unlink()
        Path(path).rmdir()

    return rmtree


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
    put(tmp_path, bundle)
    target = tmp_path / "databases" / "fixture"
    build = served_build(target)
    entry = (build / "entry.json").read_text(encoding="utf-8")
    writing = target / "builds" / "inprogress"
    writing.mkdir(parents=True)
    (writing / "entry.json").write_text(entry, encoding="utf-8")
    with install_lock(target):
        assert [d.name for d in running.databases()] == [FIXTURE_DB]
        assert writing.exists()
    running.close()
    NativeStore(tmp_path).close()
    assert not writing.exists()


def test_a_build_an_install_is_writing_survives_a_store_read_but_is_removed_when_idle(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    target = tmp_path / "databases" / "fixture"
    writing = target / "builds" / "inprogress"
    (writing / "background").mkdir(parents=True)
    (writing / "background" / "x.npy").write_bytes(b"x")
    with install_lock(target):
        NativeStore(tmp_path).databases()
        assert writing.exists()
    NativeStore(tmp_path).close()
    assert not writing.exists()


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


def test_a_format_4_install_is_moved_into_the_new_layout_and_serves_the_same_scores(
    tmp_path: Path, bundle: Path
) -> None:
    target, entry = format_4(tmp_path, bundle)

    before = score_of(Calculation(Background.load(target / "background")))

    store = NativeStore(tmp_path)
    assert [database.name for database in store.databases()] == [FIXTURE_DB]
    assert store.registered(FIXTURE_DB).database.fingerprint == entry["database"]["fingerprint"]
    assert CODES["steel"] in store.native_ids(FIXTURE_DB)
    after = score_of(store.call(FIXTURE_DB, lambda: store.calculation(FIXTURE_DB)))
    assert after == pytest.approx(before)

    builds = list((target / "builds").iterdir())
    assert len(builds) == 1
    moved = json.loads((builds[0] / "entry.json").read_text(encoding="utf-8"))
    assert moved["format"] == 5
    assert moved["database"] == entry["database"] and moved["bundle"] == entry["bundle"]
    assert (
        Background.load(builds[0] / "background").fingerprint() == entry["database"]["fingerprint"]
    )
    store.close()

    NativeStore(tmp_path).close()
    assert len(list((target / "builds").iterdir())) == 1


def test_installing_again_while_a_store_maps_the_previous_build_serves_the_new_one(
    tmp_path: Path, bundle: Path
) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    running.call(FIXTURE_DB, lambda: running.background(FIXTURE_DB))
    assert CODES["steel"] in running.native_ids(FIXTURE_DB)
    changed = renamed(tmp_path)
    put(tmp_path, changed, replace=True)
    following = NativeStore(tmp_path)
    assert steel_name(following) == "steel production, recycled"
    running.close()
    following.close()
    NativeStore(tmp_path).close()
    assert len(list((tmp_path / "databases" / "fixture" / "builds").iterdir())) == 1


def test_a_crash_after_the_background_moved_is_resumed_and_serves(
    tmp_path: Path, bundle: Path
) -> None:
    target, entry = format_4(tmp_path, bundle)
    build_id = f"migrated-{entry['bundle'][:32]}"
    half = target / "builds" / build_id
    half.mkdir(parents=True)
    shutil.move(str(target / "background"), str(half / "background"))

    store = NativeStore(tmp_path)
    assert [d.name for d in store.databases()] == [FIXTURE_DB]
    assert store.registered(FIXTURE_DB).database.fingerprint == entry["database"]["fingerprint"]
    store.close()
    assert not (target / "background").exists()
    assert not (target / "catalog.duckdb").exists()
    assert not (target / "entry.json").exists()
    assert len(list((target / "builds").iterdir())) == 1


def test_a_crash_after_the_entry_moved_is_resumed_and_serves(tmp_path: Path, bundle: Path) -> None:
    target, entry = format_4(tmp_path, bundle)
    build_id = f"migrated-{entry['bundle'][:32]}"
    half = target / "builds" / build_id
    half.mkdir(parents=True)
    shutil.move(str(target / "background"), str(half / "background"))
    shutil.move(str(target / "catalog.duckdb"), str(half / "catalog.duckdb"))
    shutil.move(str(target / "entry.json"), str(half / "entry.json"))

    store = NativeStore(tmp_path)
    assert [d.name for d in store.databases()] == [FIXTURE_DB]
    assert store.registered(FIXTURE_DB).database.fingerprint == entry["database"]["fingerprint"]
    store.close()
    moved = json.loads((half / "entry.json").read_text(encoding="utf-8"))
    assert moved["format"] == 5
    assert moved["database"] == entry["database"] and moved["bundle"] == entry["bundle"]


def test_installing_onto_a_format_4_database_migrates_then_refuses_without_replace(
    tmp_path: Path, bundle: Path
) -> None:
    target, _entry = format_4(tmp_path, bundle)
    with pytest.raises(Conflict, match="database 'fixture' is installed in"):
        put(tmp_path, bundle)
    assert (target / "current").is_file()
    assert not (target / "background").exists()
    assert not (target / "catalog.duckdb").exists()
    assert not (target / "entry.json").exists()


def test_a_store_that_loaded_only_the_background_serves_the_reinstall(
    tmp_path: Path, bundle: Path
) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    running.call(FIXTURE_DB, lambda: running.background(FIXTURE_DB))
    changed = renamed(tmp_path)
    put(tmp_path, changed, replace=True)
    assert steel_name(running) == "steel production, recycled"
    running.close()


@pytest.mark.parametrize(
    ("state", "held"),
    [("catalog", "catalog.duckdb"), ("background", "background.json")],
)
def test_a_store_serves_the_reinstall_when_windows_removal_stops_at_a_held_file(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch, state: str, held: str
) -> None:
    running = NativeStore(tmp_path)
    put(tmp_path, bundle)
    if state == "catalog":
        running.call(FIXTURE_DB, lambda: running.catalog(FIXTURE_DB))
    else:
        running.call(FIXTURE_DB, lambda: running.background(FIXTURE_DB))
    changed = renamed(tmp_path)
    monkeypatch.setattr(store_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(shutil, "rmtree", _windows_rmtree(held))
    put(tmp_path, changed, replace=True)
    if state == "catalog":
        running.call(FIXTURE_DB, lambda: running.background(FIXTURE_DB))
    assert steel_name(running) == "steel production, recycled"
    running.close()


def test_a_pointerless_build_an_install_is_writing_is_ignored_not_migrated(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    target = tmp_path / "databases" / "looped"
    writing = target / "builds" / "0123456789abcdef0123456789abcdef"
    writing.mkdir(parents=True)
    with install_lock(target):
        store = NativeStore(tmp_path)
        assert [d.name for d in store.databases()] == [FIXTURE_DB]
        assert writing.exists()
        assert not (target / "current").exists()
        store.close()
    (writing / "entry.json").write_text('{"format": 4, "marker": "untouched"}', encoding="utf-8")
    with install_lock(target):
        store = NativeStore(tmp_path)
        assert [d.name for d in store.databases()] == [FIXTURE_DB]
        assert (writing / "entry.json").read_text(encoding="utf-8") == (
            '{"format": 4, "marker": "untouched"}'
        )
        assert not (target / "current").exists()
        store.close()


def test_an_empty_builds_directory_does_not_stop_the_store_or_an_install(
    tmp_path: Path, bundle: Path
) -> None:
    put(tmp_path, bundle)
    (tmp_path / "databases" / "looped" / "builds").mkdir(parents=True)
    store = NativeStore(tmp_path)
    assert [d.name for d in store.databases()] == [FIXTURE_DB]
    store.close()
    put(tmp_path, bundle, name="looped")
    put(tmp_path, bundle, name="other")
    assert sorted(d.name for d in NativeStore(tmp_path).databases()) == [
        "fixture",
        "looped",
        "other",
    ]


def test_a_pointerless_partial_build_is_removed_when_idle(tmp_path: Path, bundle: Path) -> None:
    put(tmp_path, bundle)
    target = tmp_path / "databases" / "looped"
    writing = target / "builds" / "0123456789abcdef0123456789abcdef"
    (writing / "background").mkdir(parents=True)
    (writing / "background" / "x.npy").write_bytes(b"x")
    store = NativeStore(tmp_path)
    assert [d.name for d in store.databases()] == [FIXTURE_DB]
    assert not writing.exists()
    store.close()


def test_installing_a_format_4_database_with_replace_moves_its_root_files(
    tmp_path: Path, bundle: Path
) -> None:
    target, _entry = format_4(tmp_path, bundle)
    put(tmp_path, bundle, replace=True)
    assert not (target / "background").exists()
    assert not (target / "catalog.duckdb").exists()
    assert not (target / "entry.json").exists()
    assert (target / "current").is_file()


def test_two_installs_of_a_new_database_without_replace_serialise(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()
    release = threading.Event()
    real_compile = install_module.compile_background

    def slow(*args: object, **kwargs: object) -> object:
        entered.set()
        release.wait(10)
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(install_module, "compile_background", slow)
    first = threading.Thread(target=lambda: put(tmp_path, bundle, name="other"))
    first.start()
    assert entered.wait(10)

    raised: list[bool] = []

    def second() -> None:
        try:
            put(tmp_path, bundle, name="other")
            raised.append(False)
        except Conflict:
            raised.append(True)

    thread = threading.Thread(target=second)
    thread.start()
    release.set()
    first.join()
    thread.join()
    assert raised == [True]


def _race_an_install_committing(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch, replace: bool
) -> Path:
    """Run the idle removal while an install of "other" commits, and return its directory."""
    put(tmp_path, bundle)
    if replace:
        put(tmp_path, bundle, name="other")
    target = tmp_path / "databases" / "other"
    gate = threading.Event()
    go = threading.Event()
    real_compile = install_module.compile_background

    def slow(*args: object, **kwargs: object) -> object:
        gate.set()
        go.wait(10)
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(install_module, "compile_background", slow)
    done = threading.Event()

    def installing() -> None:
        put(tmp_path, bundle, name="other", replace=replace)
        done.set()

    thread = threading.Thread(target=installing)
    thread.start()
    assert gate.wait(10)
    real_remove = store_module.remove_unnamed_builds_if_idle

    def racing(path: Path) -> None:
        if path.name == "other" and not done.is_set():
            go.set()
            thread.join()
        real_remove(path)

    monkeypatch.setattr(store_module, "remove_unnamed_builds_if_idle", racing)
    store = NativeStore(tmp_path)
    assert sorted(d.name for d in store.databases()) == ["fixture", "other"]
    store.close()
    thread.join()
    return target


def test_a_first_install_that_commits_during_a_store_read_is_not_deleted(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _race_an_install_committing(tmp_path, bundle, monkeypatch, replace=False)
    assert (target / "current").is_file()
    assert len(list((target / "builds").iterdir())) == 1
    assert [d.name for d in NativeStore(tmp_path).databases()] == ["fixture", "other"]


def test_a_replace_that_commits_during_a_store_read_is_not_deleted(
    tmp_path: Path, bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _race_an_install_committing(tmp_path, bundle, monkeypatch, replace=True)
    assert (target / "current").is_file()
    assert len(list((target / "builds").iterdir())) == 1
    assert [d.name for d in NativeStore(tmp_path).databases()] == ["fixture", "other"]
