from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.package.package import (
    read_package,
    read_version,
    unzip_package,
    write_package,
    write_returned,
    zip_package,
)
from ecosemantic.package.sidecar import SIDECAR_DIR
from tests.dict_resolver import DictResolver

AGENT = Actor(kind="agent", id="claude")
PERSON = Actor(kind="person", name="reviewer")


def test_write_then_read(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    entry = write_package(product_system, tmp_path, AGENT, "created", resolver)
    assert entry.seq == 1 and entry.result_hash == content_hash(product_system)
    back, log = read_package(tmp_path)
    assert back.hash == entry.result_hash
    assert content_hash(back) == entry.result_hash
    assert log == [entry]
    assert read_version(tmp_path, entry.result_hash).hash == entry.result_hash
    with pytest.raises(NotFound):
        read_version(tmp_path, "0" * 64)


def test_second_write_needs_the_current_hash(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    first = write_package(product_system, tmp_path, AGENT, "created", resolver)
    stale = product_system.model_copy(deep=True)
    stale.parameters[1].value = 0.12
    with pytest.raises(Conflict):
        write_package(stale, tmp_path, AGENT, "stale", resolver)
    current, _ = read_package(tmp_path)
    current.parameters[1].value = 0.12
    second = write_package(current, tmp_path, AGENT, "waste rate", resolver)
    assert second.seq == 2 and second.base_hash == first.result_hash
    assert [c.field for c in second.changes] == ["value"]
    _, log = read_package(tmp_path)
    assert [e.seq for e in log] == [1, 2]
    assert read_version(tmp_path, first.result_hash).parameters[1].value == 0.1


def test_a_write_the_package_refuses_leaves_the_stored_state_whole(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    write_package(product_system, tmp_path, AGENT, "created", resolver)
    stored, _ = read_package(tmp_path)
    refused = stored.model_copy(deep=True)
    unknown = BackgroundRef(database=stored.database.name, id="nothing")
    refused.process("tshirt").exchanges[2].input = unknown
    with pytest.raises(NotFound):
        write_package(refused, tmp_path, AGENT, "refused", resolver)
    after, log = read_package(tmp_path)
    assert after.processes == stored.processes and [e.seq for e in log] == [1]
    noted = write_package(
        after.model_copy(update={"notes": "checked"}), tmp_path, AGENT, "noted", resolver
    )
    assert noted.seq == 2


def test_new_package_rejects_a_project_that_claims_a_base(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    claimed = product_system.model_copy(update={"hash": "0" * 64})
    with pytest.raises(Conflict):
        write_package(claimed, tmp_path, AGENT, "created", resolver)


def test_returned_package_yields_an_openlca_entry(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    retained = tmp_path / "retained"
    write_package(product_system, retained, AGENT, "created", resolver)
    exported = tmp_path / "exported"
    shutil.copytree(retained, exported)
    shutil.rmtree(exported / SIDECAR_DIR)
    (exported / "olca-schema.json").unlink()
    (exported / "openlca.json").write_text('{"schemaVersion": 2}', encoding="utf-8")
    path = exported / "processes" / f"{product_system.process('fabric').id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = "cotton fabric, woven"
    path.write_text(json.dumps(data), encoding="utf-8")
    entry = write_returned(exported, retained, PERSON, resolver)
    assert entry.source == "openlca" and entry.seq == 2 and entry.actor == PERSON
    assert [(c.entity, c.field) for c in entry.changes] == [("process", "name")]
    after, log = read_package(retained)
    assert after.process("fabric").name == "cotton fabric, woven"
    assert len(log) == 2 and log[1] == entry


def _exported_then_written(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path, notes_only: bool
) -> tuple[Path, Path]:
    """A retained package and the openLCA export taken from it at entry 1; the retained package
    then takes one more write, entry 2, which changes the notes alone or a parameter too."""
    retained = tmp_path / "retained"
    first = write_package(product_system, retained, AGENT, "created", resolver)
    exported = tmp_path / "exported"
    shutil.copytree(retained, exported)
    shutil.rmtree(exported / SIDECAR_DIR)
    later = product_system.model_copy(update={"hash": first.result_hash, "notes": "later"})
    if not notes_only:
        later = later.model_copy(deep=True)
        later.parameter("fabric_mass").value = 0.3
    write_package(later, retained, AGENT, "noted" if notes_only else "heavier fabric", resolver)
    return retained, exported


def test_a_stored_package_names_its_state_in_a_base_tag(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    entry = write_package(product_system, tmp_path, AGENT, "created", resolver)
    document = json.loads(
        (tmp_path / "product_systems" / f"{product_system.id}.json").read_text(encoding="utf-8")
    )
    assert document["tags"] == [f"ecosemantic:base={entry.result_hash}:1"]


@pytest.mark.parametrize(("notes_only", "message"), [(False, "heavier fabric"), (True, "noted")])
def test_a_return_exported_before_any_later_write_is_refused_naming_the_write(
    product_system: ProductSystem,
    resolver: DictResolver,
    tmp_path: Path,
    notes_only: bool,
    message: str,
) -> None:
    retained, exported = _exported_then_written(product_system, resolver, tmp_path, notes_only)
    expected = f"moved since the export at entry #1: #2 {message}; it is at entry #2"
    with pytest.raises(Conflict, match=expected):
        write_returned(exported, retained, PERSON, resolver)
    assert len(read_package(retained)[1]) == 2


def test_a_return_stated_at_the_current_state_returns_over_the_later_write(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    retained, exported = _exported_then_written(product_system, resolver, tmp_path, False)
    entry = write_returned(exported, retained, PERSON, resolver, at_entry=2)
    assert entry.seq == 3 and entry.source == "openlca"
    returned = read_package(retained)[0].parameter("fabric_mass").value
    assert returned == product_system.parameter("fabric_mass").value


def test_a_return_naming_no_state_is_invalid_and_one_never_reached_is_refused(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    retained, exported = _exported_then_written(product_system, resolver, tmp_path, False)
    path = exported / "product_systems" / f"{product_system.id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    stated = document["tags"][0]
    del document["tags"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(Invalid, match="names no entry it was exported at"):
        write_returned(exported, retained, PERSON, resolver)
    with pytest.raises(Conflict, match="has no entry #7; its last is #2"):
        write_returned(exported, retained, PERSON, resolver, at_entry=7)
    document["tags"] = [stated.replace(":1", ":2")]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(Conflict, match="never reached entry #2 at"):
        write_returned(exported, retained, PERSON, resolver)


def test_zip_and_unzip_round_trip(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    write_package(product_system, root, AGENT, "created", resolver)
    zipped = tmp_path / "pkg.zip"
    zip_package(root, zipped)
    out = tmp_path / "out"
    unzip_package(zipped, out)
    assert read_package(out)[0].hash == read_package(root)[0].hash
    assert (out / SIDECAR_DIR / "log.jsonl").is_file()
