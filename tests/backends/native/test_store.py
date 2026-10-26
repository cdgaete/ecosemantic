import json
import shutil
import sys
from pathlib import Path

import pytest

from ecosemantic.backends.native.store import NativeStore, slug
from ecosemantic.errors import NotFound, Unavailable
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, LOOP_DB


def test_slug_lowercases_and_joins_runs_of_other_characters() -> None:
    assert slug("ecoinvent-3.12-cutoff-native") == "ecoinvent-3-12-cutoff-native"
    assert slug("  USLCI (2025) ") == "uslci-2025"


def test_an_empty_data_directory_serves_nothing(tmp_path: Path) -> None:
    store = NativeStore(tmp_path)
    assert store.databases() == []
    store.close()


def test_the_store_serves_every_installed_database_by_name(native_store: NativeStore) -> None:
    assert [d.name for d in native_store.databases()] == [FIXTURE_DB, LOOP_DB]
    assert native_store.technosphere_of(FIXTURE_BIO) == FIXTURE_DB
    assert native_store.owner_of_elementary_flows(FIXTURE_BIO) == FIXTURE_DB
    assert native_store.bundle_of(FIXTURE_DB).is_file()
    assert CODES["steel"] in native_store.native_ids(FIXTURE_DB)


def test_names_the_store_does_not_serve_are_not_found(native_store: NativeStore) -> None:
    with pytest.raises(NotFound, match="holds the elementary flows of 'fixture'; name 'fixture'"):
        native_store.registered(FIXTURE_BIO)
    with pytest.raises(NotFound, match="no database 'nowhere' under"):
        native_store.registered("nowhere")
    with pytest.raises(NotFound, match="this store serves \\['fixture', 'looped'\\]"):
        native_store.technosphere_of("nowhere")
    with pytest.raises(NotFound, match="uses the elementary flows 'nowhere'"):
        native_store.owner_of_elementary_flows("nowhere")


def test_a_calculation_is_loaded_once_per_database(native_store: NativeStore) -> None:
    first = native_store.call(FIXTURE_DB, lambda: native_store.calculation(FIXTURE_DB))
    again = native_store.call(FIXTURE_DB, lambda: native_store.calculation(FIXTURE_DB))
    assert first is again and first.solver.name == "superlu"


def test_a_calculation_stands_on_the_background_the_store_loads(native_store: NativeStore) -> None:
    background = native_store.call(FIXTURE_DB, lambda: native_store.background(FIXTURE_DB))
    calculation = native_store.call(FIXTURE_DB, lambda: native_store.calculation(FIXTURE_DB))
    again = native_store.call(FIXTURE_DB, lambda: native_store.background(FIXTURE_DB))
    assert calculation.background is background is again


def test_two_stores_read_one_catalog_at_once(bundle_dir: Path, native_store: NativeStore) -> None:
    other = NativeStore(bundle_dir)
    assert other.native_ids(FIXTURE_DB) == native_store.native_ids(FIXTURE_DB)
    other.close()


def test_a_directory_whose_name_starts_with_a_dot_is_not_read(
    tmp_path: Path, bundle_dir: Path
) -> None:
    shutil.copytree(
        bundle_dir / "databases" / "fixture", tmp_path / "databases" / ".fixture.partial-x"
    )
    assert NativeStore(tmp_path).databases() == []


def test_an_entry_of_format_3_is_refused_with_its_remedy(tmp_path: Path, bundle_dir: Path) -> None:
    target = tmp_path / "databases" / "fixture"
    shutil.copytree(bundle_dir / "databases" / "fixture", target)
    entry = json.loads((target / "entry.json").read_text())
    held = {"format": 3, "database": entry["database"], "bundle": entry["bundle"]}
    (target / "entry.json").write_text(json.dumps(held))
    with pytest.raises(Unavailable, match="entry format 3; this store reads format 4") as raised:
        NativeStore(tmp_path)
    assert raised.value.hint == (
        "install it again from its bundle with `ecosemantic setup openlca --replace`"
    )


def test_a_store_under_pardiso_without_pypardiso_is_refused_when_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a module table entry of None makes `import pypardiso` raise ImportError
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    with pytest.raises(Unavailable, match="pypardiso"):
        NativeStore(tmp_path, solver="pardiso")
