from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.package.base import BaseBundle
from tests.openlca_fixture import FLOW_IDS, PROCESSES, build_package


@pytest.fixture
def package(tmp_path: Path) -> Path:
    return build_package(tmp_path / "base.zip")


def test_the_closure_follows_providers_by_the_readers_rule(package: Path) -> None:
    with BaseBundle(package) as base:
        assert base.closure([PROCESSES["steel"]]) == {PROCESSES["steel"], PROCESSES["elec"]}
        # the widget's fuel names no provider; its one producer is the refinery
        assert PROCESSES["refinery"] in base.closure([PROCESSES["widget"]])
        with pytest.raises(NotFound, match="missing"):
            base.closure(["missing"])


def test_the_copy_is_byte_identical_and_carries_what_the_processes_name(
    package: Path, tmp_path: Path
) -> None:
    target = tmp_path / "out.zip"
    with BaseBundle(package) as base, zipfile.ZipFile(target, "w") as out:
        written = base.copy(out, {PROCESSES["steel"], PROCESSES["elec"]})
    with zipfile.ZipFile(package) as src, zipfile.ZipFile(target) as dst:
        for member in written:
            assert dst.read(member) == src.read(member)
        names = set(dst.namelist())
    assert f"processes/{PROCESSES['widget']}.json" not in names
    assert {
        f"flows/{FLOW_IDS[k]}.json" for k in ("steel", "electricity", "co2", "ch4", "water")
    } <= names
    assert any(n.startswith("lcia_methods/") for n in names)
    assert any(n.startswith("unit_groups/") for n in names)


def test_a_base_flows_unit_is_any_of_its_group_named_by_the_models_long_name(
    package: Path,
) -> None:
    with BaseBundle(package) as base:
        unit, prop = base.flow_unit(FLOW_IDS["electricity"], "megajoule")
        assert unit.name == "MJ" and prop.name == "Energy"
        kwh, _ = base.flow_unit(FLOW_IDS["electricity"], "kilowatt hour")
        assert kwh.name == "kWh"
        with pytest.raises(Invalid, match="electricity, medium voltage.*kilogram"):
            base.flow_unit(FLOW_IDS["electricity"], "kilogram")
        assert base.is_resource(FLOW_IDS["water"]) and not base.is_resource(FLOW_IDS["co2"])


def test_a_base_process_links_each_input_to_its_provider(package: Path) -> None:
    with BaseBundle(package) as base:
        links = base.links({PROCESSES["steel"]})
    assert [
        (link["provider"]["@id"], link["flow"]["@id"], link["exchange"]["internalId"])
        for link in links
    ] == [(PROCESSES["elec"], FLOW_IDS["electricity"], 2)]
