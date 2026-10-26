"""Build a USLCI release and its methods into one openLCA bundle the core imports."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ecosemantic.databases.lists import read_left_out
from ecosemantic.databases.scores import score_every_dataset
from ecosemantic.databases.uslci.build import Built, build
from ecosemantic.errors import Conflict, Invalid
from ecosemantic.package.background import Import, read_background
from tests.databases.uslci_fixture import (
    BRIDGED_CODES,
    BRIDGED_NAME,
    BRIDGED_PROCESSES,
    BRIDGES,
    CLIMATE,
    CODES,
    EXPECTED,
    FLOW_NAMES,
    INVENTORY_NAME,
    METHOD_NAME,
    PROCESSES,
    _described,
    _flow_id,
    _id,
    _property_id,
    _unit,
    write_bridged,
    write_inventory,
    write_method,
)

VERSION = "1.2026-09.0"
WIDGET = PROCESSES["widget"]


@pytest.fixture
def built(tmp_path: Path) -> Built:
    return build(
        write_inventory(tmp_path / INVENTORY_NAME),
        (write_method(tmp_path / METHOD_NAME),),
        version=VERSION,
        out_dir=tmp_path / "out",
    )


@pytest.fixture
def merged(tmp_path: Path) -> Built:
    """The release built with the repository its bridges link to beside it."""
    return build(
        write_inventory(tmp_path / INVENTORY_NAME),
        (write_method(tmp_path / METHOD_NAME),),
        version=VERSION,
        out_dir=tmp_path / "out",
        bridged=(write_bridged(tmp_path / BRIDGED_NAME),),
    )


def _record(bundle: Path, folder: str, entity_id: str) -> dict[str, object]:
    with zipfile.ZipFile(bundle) as archive:
        return json.loads(archive.read(f"{folder}/{entity_id}.json"))


def _members(bundle: Path) -> list[str]:
    with zipfile.ZipFile(bundle) as archive:
        return sorted(archive.namelist())


def _imported(built: Built) -> Import:
    return read_background(built.bundle, "uslci", foreground=frozenset())


def _exchange(process: dict[str, object], internal_id: int) -> dict[str, object]:
    return next(
        exchange for exchange in process["exchanges"] if exchange["internalId"] == internal_id
    )


def test_the_bundle_holds_the_used_and_the_characterised_elementary_flows(built: Built) -> None:
    assert built.elementary_flows == EXPECTED["bundle"]["elementary_flows"]
    members = _members(built.bundle)
    assert f"flows/{_flow_id('so2')}.json" not in members
    assert f"flows/{_flow_id('nox')}.json" in members
    assert built.processes == EXPECTED["processes"]
    assert (built.methods, built.categories) == (EXPECTED["methods"], EXPECTED["categories"])
    assert built.converted == EXPECTED["bundle"]["converted"]


def test_the_inventory_s_record_wins_where_both_zips_hold_an_id(
    built: Built, tmp_path: Path
) -> None:
    with zipfile.ZipFile(tmp_path / INVENTORY_NAME) as archive:
        inventory = json.loads(archive.read(f"flows/{_flow_id('co2')}.json"))
    assert _record(built.bundle, "flows", _flow_id("co2")) == inventory


def test_a_bridge_links_to_the_provider_its_description_names(merged: Built) -> None:
    link = _exchange(_record(merged.bundle, "processes", BRIDGES["Electricity Bridge; GRID"]), 2)
    assert link["defaultProvider"] == {
        "@type": "Process",
        "@id": BRIDGED_PROCESSES["grid mix"],
        "name": "grid mix",
    }
    assert link["description"] == _described(BRIDGED_PROCESSES["grid mix"])
    assert merged.bridges_linked == EXPECTED["bridged"]["bridges_linked"]


def test_a_bridge_naming_a_missing_process_stays_unlinked(merged: Built) -> None:
    nowhere = _exchange(
        _record(merged.bundle, "processes", BRIDGES["Electricity Bridge; NOWHERE"]), 2
    )
    assert "defaultProvider" not in nowhere
    assert merged.bridges_unlinked == EXPECTED["bridged"]["bridges_unlinked"]
    assert ("Electricity Bridge; NOWHERE", "electricity") in {
        (miss.process, miss.flow) for miss in _imported(merged).unlinked
    }


@pytest.mark.parametrize(
    "description",
    [
        "an ordinary note",
        json.dumps({"comment": "", "note": "no provider here"}),
        json.dumps(["no", "provider"]),
    ],
    ids=["text", "json", "not-an-object"],
)
def test_a_description_that_is_no_provider_changes_nothing(
    tmp_path: Path, description: str
) -> None:
    built = build(
        write_inventory(tmp_path / INVENTORY_NAME, grid_description=description),
        (write_method(tmp_path / METHOD_NAME),),
        version=VERSION,
        out_dir=tmp_path / "out",
        bridged=(write_bridged(tmp_path / BRIDGED_NAME),),
    )
    link = _exchange(_record(built.bundle, "processes", BRIDGES["Electricity Bridge; GRID"]), 2)
    assert link["description"] == description
    assert "defaultProvider" not in link
    assert built.bridges_linked == 0
    assert built.bridges_unlinked == EXPECTED["bridged"]["bridges_unlinked"]


def test_uslci_s_record_wins_a_shared_id(merged: Built, tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / INVENTORY_NAME) as archive:
        inventory = json.loads(archive.read(f"flows/{_flow_id('electricity')}.json"))
    with zipfile.ZipFile(tmp_path / BRIDGED_NAME) as archive:
        bridged = json.loads(archive.read(f"flows/{_flow_id('electricity')}.json"))
    assert bridged["description"] != inventory["description"]
    assert _record(merged.bundle, "flows", _flow_id("electricity")) == inventory


def test_a_bridged_exchange_converts_with_its_own_units(merged: Built) -> None:
    coal = _exchange(_record(merged.bundle, "processes", BRIDGED_PROCESSES["coal plant"]), 2)
    assert coal["amount"] == EXPECTED["bridged"]["coal"]["amount"]
    assert coal["unit"] == {"@type": "Unit", "@id": _unit("mass", "kg"), "name": "kg"}
    assert merged.unit_converted == EXPECTED["bridged"]["unit_converted"]


def test_a_bridged_exchange_moves_to_its_flow_s_reference_property(merged: Built) -> None:
    crude = _exchange(_record(merged.bundle, "processes", BRIDGED_PROCESSES["grid mix"]), 2)
    assert crude["amount"] == EXPECTED["bridged"]["crude"]["amount"]
    assert crude["flowProperty"]["@id"] == _property_id("energy")
    assert crude["flowProperty"]["name"] == EXPECTED["bridged"]["crude"]["property"]
    assert crude["unit"] == {"@type": "Unit", "@id": _unit("energy", "MJ"), "name": "MJ"}
    assert merged.converted == EXPECTED["bridged"]["converted"]


def test_the_merged_bundle_scores_as_computed_by_hand(merged: Built) -> None:
    imported = _imported(merged)
    assert len(imported.datasets) == EXPECTED["bridged"]["datasets"]
    scores = score_every_dataset(imported, name="uslci")
    codes = CODES | BRIDGED_CODES
    for role, expected in EXPECTED["bridged"]["scores"].items():
        for category, score in expected.items():
            assert scores.values[(codes[role], "IPCC GWP", category)] == pytest.approx(
                score, rel=1e-12
            )


def test_a_factor_unit_under_another_id_is_matched_by_name(built: Built) -> None:
    category = _record(built.bundle, "lcia_categories", _id("category", CLIMATE))
    factors = {factor["flow"]["name"]: factor for factor in category["impactFactors"]}
    # the carbon dioxide factor names the method's kg; only the inventory's group shares that name
    carbon = factors["Carbon dioxide, fossil"]
    assert carbon["unit"]["name"] == "kg"
    assert carbon["unit"]["@id"] == _unit("mass", "kg")
    nitrogen = factors["Nitrogen oxides"]
    assert nitrogen["unit"]["@id"] == _unit("method mass", "kg")


def test_a_factor_in_a_property_its_flow_lacks_stops_the_build(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME, stray_property=True)
    with pytest.raises(Invalid) as refused:
        build(inventory, (method,), version=VERSION, out_dir=tmp_path / "out")
    message = str(refused.value)
    assert "IPCC GWP" in message
    assert CLIMATE in message
    assert "Carbon dioxide, fossil" in message


def test_the_converted_exchange_takes_its_flow_s_reference_property_and_unit(built: Built) -> None:
    process = _record(built.bundle, "processes", WIDGET)
    water = _exchange(process, 4)
    converted = EXPECTED["converted"]
    assert water["amount"] == converted["amount"]
    assert water["flowProperty"]["@id"] == _property_id("mass")
    assert water["unit"] == {"@type": "Unit", "@id": _unit("mass", "kg"), "name": "kg"}
    assert water["uncertainty"]["geomMean"] == converted["geom_mean"]
    assert water["uncertainty"]["geomSd"] == converted["geom_sd"]
    assert water["amountFormula"] == converted["formula"]


def test_a_converted_exchange_without_a_distribution_or_a_formula_gains_neither(
    tmp_path: Path,
) -> None:
    built = build(
        write_inventory(tmp_path / INVENTORY_NAME, bare_conversion=True),
        (write_method(tmp_path / METHOD_NAME),),
        version=VERSION,
        out_dir=tmp_path / "out",
    )
    water = _exchange(_record(built.bundle, "processes", WIDGET), 4)
    assert water["amount"] == EXPECTED["converted"]["amount"]
    assert "uncertainty" not in water
    assert "amountFormula" not in water


def test_a_rewritten_record_keeps_every_field_it_does_not_change(
    built: Built, tmp_path: Path
) -> None:
    with zipfile.ZipFile(tmp_path / INVENTORY_NAME) as archive:
        source = json.loads(archive.read(f"processes/{WIDGET}.json"))
    written = _record(built.bundle, "processes", WIDGET)
    assert written["lastInternalId"] == source["lastInternalId"]
    assert set(written) == set(source)
    moved = {"amount", "amountFormula", "flowProperty", "unit", "uncertainty"}
    for key in set(source) - {"exchanges"}:
        assert written[key] == source[key]
    before = _exchange(source, 4)
    after = _exchange(written, 4)
    assert set(after) == set(before)
    for key in set(before) - moved:
        assert after[key] == before[key]


def test_what_the_core_cannot_hold_is_left_out_and_listed(built: Built, tmp_path: Path) -> None:
    steel = _record(built.bundle, "processes", PROCESSES["steel"])
    assert "uncertainty" not in _exchange(steel, 3)
    widget = _record(built.bundle, "processes", WIDGET)
    written = [exchange["internalId"] for exchange in widget["exchanges"]]
    assert 7 not in written
    assert 8 in written
    expected = {
        (row["process"], row["exchange"], row["what"]): row["reason"]
        for row in EXPECTED["left_out"]
    }
    assert {
        (row.process_name, row.exchange_id, row.what): row.reason for row in built.left_out
    } == expected
    assert read_left_out(tmp_path / "out" / f"left-out-{VERSION}.csv") == built.left_out


def test_the_core_imports_the_bundle(built: Built) -> None:
    imported = _imported(built)
    assert len(imported.datasets) == EXPECTED["bundle"]["datasets"]
    assert len(imported.flows) == EXPECTED["bundle"]["elementary_flows"]
    assert len(imported.methods) == EXPECTED["categories"]
    assert sorted(CODES.values()) == sorted(code for _, code in imported.datasets)
    assert {(miss.process, miss.flow, miss.provider_id) for miss in imported.unlinked} == {
        (row["process"], FLOW_NAMES[row["flow"]], row["provider"]) for row in EXPECTED["unlinked"]
    }


def test_a_bundle_whose_exchange_names_a_flow_it_lacks_is_refused_by_name(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME, dangling_flow=True)
    with pytest.raises(Invalid) as refused:
        build(
            inventory,
            (write_method(tmp_path / METHOD_NAME),),
            version=VERSION,
            out_dir=tmp_path / "out",
        )
    message = str(refused.value)
    assert "widget" in message
    assert "its flow" in message
    assert not list((tmp_path / "out").glob("*.partial"))


def test_the_archive_s_directory_entries_are_carried_and_not_counted(built: Built) -> None:
    members = _members(built.bundle)
    assert built.methods == EXPECTED["methods"]
    assert built.categories == EXPECTED["categories"]
    assert "flows/" in members
    assert any(name.startswith("bin/") for name in members)


def test_a_flag_the_export_omits_is_read_as_false(built: Built) -> None:
    water = _record(built.bundle, "flows", _flow_id("water"))
    assert [item.get("isRefFlowProperty") for item in water["flowProperties"]] == [True, None]
    mass = _record(built.bundle, "unit_groups", _id("group", "mass"))
    assert [unit.get("isRefUnit") for unit in mass["units"]] == [True, None]


def test_an_exchange_in_a_unit_uslci_defines_otherwise_takes_uslci_s_factor(
    built: Built,
) -> None:
    widget = _record(built.bundle, "processes", WIDGET)
    methane = _exchange(widget, 6)
    assert built.unit_converted == EXPECTED["unit_factors_differ"]
    assert methane["amount"] == EXPECTED["methane"]["amount"]
    assert methane["unit"]["name"] == EXPECTED["methane"]["unit"]


def test_an_exchange_in_a_unit_the_core_lacks_takes_the_release_s_factor(
    tmp_path: Path,
) -> None:
    built = build(
        write_inventory(tmp_path / INVENTORY_NAME, odd_unit=True),
        (write_method(tmp_path / METHOD_NAME),),
        version=VERSION,
        out_dir=tmp_path / "out",
    )
    methane = _exchange(_record(built.bundle, "processes", WIDGET), 6)
    assert methane["unit"]["name"] == "kg"
    assert methane["amount"] == 100.0
    assert built.unit_converted == {"furlong": 1}


def test_a_product_declared_in_litres_keeps_its_unit(built: Built) -> None:
    distillery = _record(built.bundle, "processes", PROCESSES["distillery"])
    ethanol = _exchange(distillery, 1)
    assert ethanol["amount"] == 1.0
    assert ethanol["unit"]["name"] == "l"
    assert "l" not in built.unit_converted


def test_an_existing_destination_is_a_conflict(built: Built, tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / "another-inventory.zip")
    with pytest.raises(Conflict, match="exists"):
        build(inventory, (), version=VERSION, out_dir=tmp_path / "out")
