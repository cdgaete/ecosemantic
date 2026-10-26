from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.compute.links import linked_documents
from ecosemantic.compute.overrides import apply_case
from ecosemantic.compute.parameters import materialize
from ecosemantic.compute.render import product_flow_id
from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import DemandItem, Method, ProductSystem
from ecosemantic.model.refs import BackgroundRef, ForegroundRef, SystemRef
from ecosemantic.package.background import read_background
from ecosemantic.package.manifest import CHANGELOG, BaseDatabase, Changelog, read_manifest
from ecosemantic.package.release import build_release
from ecosemantic.package.wholeness import misses
from ecosemantic.ports.types import System
from tests.database_fixture import BASE
from tests.openlca_fixture import METHOD
from tests.package.conftest import AGENT, BASE_DB, NOW, Bench


def _methods(database: str) -> list[Method]:
    return [
        Method.of((database, METHOD, "climate change"), "kg CO2-Eq"),
        Method.of((database, METHOD, "water use"), "m3"),
    ]


async def _platform(
    calculation: NativeCalculation, bench: Bench, system: ProductSystem, case: str | None
) -> list[float]:
    resolved = apply_case(system, system.case(case)) if case else materialize(system)
    linked = await linked_documents(system, bench.storage.get_version)
    demand = [DemandItem(ref=ForegroundRef(code=system.reference_process), amount=1.0)]
    scores = await calculation.scores(System.of(resolved, linked), demand, _methods(BASE))
    return [s.value for s in scores]


async def test_a_release_scores_every_reference_dataset_as_the_platform_does(bench: Bench) -> None:
    target = bench.root / "release.zip"
    manifest = await build_release(
        bench.storage, bench.base_bundle, BASE_DB, "release", "1", target, None, NOW
    )
    assert misses(target) == [] and read_manifest(target) == manifest
    assert {(d.process_code, d.case) for d in manifest.datasets} == {
        ("assembly", "light"),
        ("casing", "light"),
        ("assembly", "heavy"),
        ("casing", "heavy"),
        ("device", "base"),
    }
    imported = read_background(target, "release", foreground=frozenset())
    install(bench.store.directory, imported, target, version="1", system_model="unit process")
    store = NativeStore(bench.store.directory)
    calculation = NativeCalculation(store)
    systems = {bench.casing.id: bench.casing, bench.device.id: bench.device}
    for dataset in manifest.datasets:
        system = systems[dataset.product_system_id]
        if dataset.process_code != system.reference_process:
            continue
        ref = BackgroundRef(
            database="release",
            id=f"{dataset.id}_{product_flow_id(system.id, dataset.process_code)}",
        )
        released = await calculation.scores(
            System(database="release"), [DemandItem(ref=ref, amount=1.0)], _methods("release")
        )
        case = None if dataset.case == "base" else dataset.case
        platform = await _platform(calculation, bench, system, case)
        for got, want in zip([s.value for s in released], platform, strict=True):
            assert got == pytest.approx(want, rel=1e-12)
    store.close()


async def test_a_second_release_says_what_changed(bench: Bench) -> None:
    first = bench.root / "r1.zip"
    await build_release(bench.storage, bench.base_bundle, BASE_DB, "release", "1", first, None, NOW)
    edited = bench.device.model_copy(deep=True)
    edited.process("device").exchanges[2].amount = 0.3
    await bench.storage.put_product_system(edited, AGENT, "more direct CO2")
    second = bench.root / "r2.zip"
    manifest = await build_release(
        bench.storage, bench.base_bundle, BASE_DB, "release", "2", second, first, NOW
    )
    log = changelog_of(second)
    device = [d.id for d in manifest.datasets if d.process_code == "device"]
    assert log.changed == device and log.added == [] and log.removed == []
    assert len(log.unchanged) == 4 and log.previous == "1"


async def test_the_gates_refuse_before_anything_is_written(bench: Bench) -> None:
    taken = bench.root / "taken.zip"
    taken.write_bytes(b"")
    with pytest.raises(Conflict, match="taken.zip"):
        await build_release(
            bench.storage, bench.base_bundle, BASE_DB, "release", "1", taken, None, NOW
        )
    with pytest.raises(Invalid, match="not on"):
        await build_release(
            bench.storage,
            bench.base_bundle,
            BaseDatabase(name="other", version="1"),
            "release",
            "1",
            bench.root / "a.zip",
            None,
            NOW,
        )
    edited = bench.casing.model_copy(deep=True)
    edited.process("casing").exchanges[2].amount = 0.07
    await bench.storage.put_product_system(edited, AGENT, "edit behind the link")
    with pytest.raises(Invalid, match="device"):
        await build_release(
            bench.storage,
            bench.base_bundle,
            BASE_DB,
            "release",
            "1",
            bench.root / "b.zip",
            None,
            NOW,
        )
    assert not (bench.root / "b.zip").exists() and not (bench.root / "b.zip.partial").exists()


async def test_a_link_naming_no_case_of_a_system_with_cases_is_refused(bench: Bench) -> None:
    caseless = bench.device.model_copy(deep=True)
    link = caseless.process("device").exchanges[1]
    link.input = SystemRef(product_system_id=bench.casing.id, at_hash=bench.casing.hash, case=None)
    await bench.storage.put_product_system(caseless, AGENT, "link the casing's base")
    with pytest.raises(NotFound, match="casing"):
        await build_release(
            bench.storage,
            bench.base_bundle,
            BASE_DB,
            "release",
            "1",
            bench.root / "c.zip",
            None,
            NOW,
        )


def changelog_of(bundle: Path) -> Changelog:
    with zipfile.ZipFile(bundle) as zipped:
        return Changelog.model_validate_json(zipped.read(CHANGELOG))
