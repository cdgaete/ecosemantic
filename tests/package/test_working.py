from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.model.refs import SystemRef, keygen
from ecosemantic.package.background import read_background
from ecosemantic.package.release import build_release
from ecosemantic.package.wholeness import misses
from ecosemantic.package.working import build_working, foreground_processes, restore_systems
from tests.database_fixture import BASE, backgrounds, flows
from tests.dict_resolver import DictResolver
from tests.openlca_fixture import FLOW_IDS, PROCESSES
from tests.package.conftest import AGENT, BASE_DB, NOW, Bench


async def test_a_working_database_saves_and_loads_every_system_at_its_state(
    bench: Bench, tmp_path: Path
) -> None:
    target = tmp_path / "working.zip"
    manifest = await build_working(
        bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW
    )
    assert manifest.mode == "working" and misses(target) == []
    elsewhere = FilesystemStorage(tmp_path / "elsewhere", DictResolver(backgrounds(), flows()))
    assert await restore_systems(target, elsewhere) == {
        bench.casing.id: "added",
        bench.device.id: "added",
    }
    for system in (bench.casing, bench.device):
        back = await elsewhere.get_product_system(system.id)
        assert back.hash == system.hash and back.cases == system.cases
        assert await elsewhere.log(system.id) == await bench.storage.log(system.id)
    assert await restore_systems(target, elsewhere) == {
        bench.casing.id: "unchanged",
        bench.device.id: "unchanged",
    }


async def test_a_base_flow_the_packages_stub_keeps_the_bases_bytes(
    bench: Bench, tmp_path: Path
) -> None:
    target = tmp_path / "working.zip"
    await build_working(bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW)
    member = f"flows/{FLOW_IDS['steel']}.json"
    with zipfile.ZipFile(bench.base_bundle) as base, zipfile.ZipFile(target) as work:
        assert work.read(member) == base.read(member)
        assert work.namelist().count(member) == 1


async def test_foreground_processes_install_nothing_and_a_held_base_is_kept(
    bench: Bench, tmp_path: Path
) -> None:
    target = tmp_path / "working.zip"
    await build_working(bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW)
    foreground = foreground_processes(target)
    assert {str(p.id) for s in (bench.casing, bench.device) for p in s.processes} == set(foreground)
    imported = read_background(target, BASE, foreground=foreground)
    assert {code for _, code in imported.datasets} <= bench.store.native_ids(BASE)


async def test_a_working_systems_graph_reaches_its_base_supply_chain(
    bench: Bench, tmp_path: Path
) -> None:
    target = tmp_path / "working.zip"
    await build_working(bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW)
    with zipfile.ZipFile(target) as zipped:
        system = json.loads(zipped.read(f"product_systems/{bench.casing.id}.json"))
    assert {PROCESSES["steel"], PROCESSES["elec"]} <= {p["@id"] for p in system["processes"]}
    links = {(link["provider"]["@id"], link["process"]["@id"]) for link in system["processLinks"]}
    casing = str(bench.casing.process("casing").id)
    assert {(PROCESSES["steel"], casing), (PROCESSES["elec"], PROCESSES["steel"])} <= links


async def test_a_linking_system_carries_the_linked_case_as_redefinitions(
    bench: Bench, tmp_path: Path
) -> None:
    target = tmp_path / "working.zip"
    await build_working(bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW)
    with zipfile.ZipFile(target) as zipped:
        device = json.loads(zipped.read(f"product_systems/{bench.device.id}.json"))
    # the device links the casing's heavy case: 0.8 kg casing, 0.1 kg coating
    [chosen] = device["parameterSets"]
    assert (chosen["name"], chosen["isBaseline"]) == ("base", True)
    assert sorted((r["name"], r["value"]) for r in chosen["parameters"]) == [
        ("casing__casing_mass", 0.8),
        ("casing__coating_mass", 0.1),
    ]


async def test_a_link_naming_no_case_saves_under_the_linked_base_values(
    bench: Bench, tmp_path: Path
) -> None:
    caseless = bench.device.model_copy(deep=True)
    link = caseless.process("device").exchanges[1]
    link.input = SystemRef(product_system_id=bench.casing.id, at_hash=bench.casing.hash, case=None)
    await bench.storage.put_product_system(caseless, AGENT, "link the casing's base")
    target = tmp_path / "working.zip"
    manifest = await build_working(
        bench.storage, bench.base_bundle, BASE_DB, "work", "1", target, NOW
    )
    assert manifest.mode == "working"


def _base_holding_the_packages_location(bench: Bench, tmp_path: Path) -> tuple[Path, str]:
    member = f"locations/{keygen('GLO')}.json"
    widened = tmp_path / "widened.zip"
    with zipfile.ZipFile(bench.base_bundle) as src, zipfile.ZipFile(widened, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr(
            member,
            json.dumps({"@type": "Location", "@id": keygen("GLO"), "name": "GLO", "code": "GLO"}),
        )
    return widened, member


async def test_a_record_the_base_holds_outside_the_closure_is_written_from_the_base(
    bench: Bench, tmp_path: Path
) -> None:
    widened, member = _base_holding_the_packages_location(bench, tmp_path)
    working, release = tmp_path / "working.zip", tmp_path / "release.zip"
    await build_working(bench.storage, widened, BASE_DB, "work", "1", working, NOW)
    await build_release(bench.storage, widened, BASE_DB, "rel", "1", release, None, NOW)
    for bundle in (working, release):
        with zipfile.ZipFile(bundle) as built, zipfile.ZipFile(widened) as base:
            assert built.read(member) == base.read(member)
