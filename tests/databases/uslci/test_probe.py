"""Probe a USLCI release and its method for what a build reads, on the synthetic pair of zips."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ecosemantic.databases.uslci.probe import Probe, probe
from ecosemantic.errors import Invalid
from tests.databases.uslci_fixture import (
    BRIDGED_NAME,
    EXPECTED,
    INVENTORY_NAME,
    METHOD_NAME,
    write_bridged,
    write_inventory,
    write_method,
)


@pytest.fixture
def probed(tmp_path: Path) -> Probe:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    return probe(inventory, (write_method(tmp_path / METHOD_NAME),))


def test_the_probe_reads_each_package_s_schema_version(probed: Probe) -> None:
    assert probed.schema_versions == EXPECTED["schema_versions"]


def test_the_probe_counts_the_processes_and_the_elementary_flows(probed: Probe) -> None:
    assert probed.processes == EXPECTED["processes"]
    assert probed.elementary_flows == EXPECTED["elementary_flows"]


def test_the_probe_counts_the_methods_and_their_categories(probed: Probe) -> None:
    assert probed.methods == EXPECTED["methods"]
    assert probed.categories == EXPECTED["categories"]


def test_the_probe_counts_the_flows_a_method_characterises_that_the_release_uses(
    probed: Probe,
) -> None:
    assert probed.characterised == EXPECTED["characterised"]


def test_a_method_naming_a_category_the_package_lacks_counts_no_flow_for_it(
    tmp_path: Path,
) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME, dangling_category=True)
    probed = probe(inventory, (method,))
    assert probed.characterised == EXPECTED["characterised"]
    assert probed.categories == EXPECTED["categories"]


def test_the_probe_finds_no_unit_symbol_the_core_lacks(probed: Probe) -> None:
    assert probed.unknown_units == EXPECTED["unknown_units"]


def test_the_probe_names_the_unit_symbol_the_core_lacks(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME, odd_unit=True)
    probed = probe(inventory, (write_method(tmp_path / METHOD_NAME),))
    assert probed.unknown_units == {"furlong": 1}


def test_the_probe_counts_the_one_exchange_in_another_flow_property(probed: Probe) -> None:
    assert probed.other_property == EXPECTED["other_property"]


def test_the_probe_counts_the_distribution_and_the_exchange_the_importer_refuses(
    probed: Probe,
) -> None:
    assert probed.refused == EXPECTED["refused"]


def test_the_probe_counts_the_units_the_release_defines_otherwise(probed: Probe) -> None:
    assert probed.unit_factors_differ == EXPECTED["unit_factors_differ"]


def test_probe_counts_the_one_cut_off_under_its_category(probed: Probe) -> None:
    assert probed.unlinked_by_category == EXPECTED["unlinked_by_category"]
    assert probed.build_refused is EXPECTED["build_refused"]


def test_probe_counts_the_bridges(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    probed = probe(
        inventory,
        (write_method(tmp_path / METHOD_NAME),),
        bridged=(write_bridged(tmp_path / BRIDGED_NAME),),
    )
    assert probed.bridges_linked == EXPECTED["bridged"]["bridges_linked"]
    assert probed.bridges_unlinked == EXPECTED["bridged"]["bridges_unlinked"]
    assert probed.schema_versions[BRIDGED_NAME] == 2
    assert probed.build_refused is None


def test_a_build_that_stops_is_what_the_probe_reports(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME, stray_property=True)
    probed = probe(inventory, (method,))
    assert probed.unlinked_by_category == {}
    assert probed.build_refused is not None
    assert "Carbon dioxide, fossil" in probed.build_refused


def test_the_probe_writes_nothing_beside_the_packages(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    probe(inventory, (write_method(tmp_path / METHOD_NAME),))
    assert sorted(path.name for path in tmp_path.iterdir()) == [METHOD_NAME, INVENTORY_NAME]


def test_a_package_declaring_no_schema_version_is_invalid(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    with zipfile.ZipFile(inventory) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(inventory, mode="w") as rewritten:
        for name, content in members.items():
            if name != "openlca.json":
                rewritten.writestr(name, content)
    with pytest.raises(Invalid, match="openlca.json"):
        probe(inventory, (write_method(tmp_path / METHOD_NAME),))
