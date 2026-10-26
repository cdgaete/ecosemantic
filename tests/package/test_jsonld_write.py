from __future__ import annotations

import json
import uuid
from pathlib import Path

import olca_schema as o
import pytest

from ecosemantic.errors import NotFound, NotSupported
from ecosemantic.model import units
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import (
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    keygen,
    olca_process_id,
    olca_product_flow_id,
)
from ecosemantic.package.jsonld import (
    DESCRIPTOR,
    UnitTable,
    parameter_prefix,
    rewrite_formula,
    strip_prefix,
    write_jsonld,
)
from ecosemantic.package.sidecar import supplier_key
from ecosemantic.ports.resolver import FlowInfo
from tests.conftest import COTTON, ELEC_CH
from tests.dict_resolver import DictResolver


def test_formula_rewriting_is_reversible() -> None:
    names = {"fabric_mass", "waste_rate"}
    out = rewrite_formula("fabric_mass * (1 + waste_rate) + sqrt(fabric_mass)", names, "p__")
    assert out == "p__fabric_mass * (1 + p__waste_rate) + sqrt(p__fabric_mass)"
    assert strip_prefix(out, "p__") == "fabric_mass * (1 + waste_rate) + sqrt(fabric_mass)"


def test_writer_lays_out_the_package(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    identities = write_jsonld(product_system, tmp_path, resolver)
    assert (tmp_path / DESCRIPTOR).is_file()
    assert len(list((tmp_path / "processes").glob("*.json"))) == 4
    assert len(list((tmp_path / "product_systems").glob("*.json"))) == 1
    assert len(list((tmp_path / "parameters").glob("*.json"))) == 5
    assert identities.parameter_prefix == parameter_prefix(product_system) == "cotton_tshirt__"
    assert len(identities.processes) == 4
    assert len(identities.exchanges) == 17
    assert set(identities.locations.values()) == {"CH", "GLO"}


def test_writer_derives_background_ids_and_prefixes_parameters(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    identities = write_jsonld(product_system, tmp_path, resolver)
    elec_key = supplier_key(
        olca_process_id("ecoinvent", ELEC_CH.id), olca_product_flow_id("ecoinvent", ELEC_CH.id)
    )
    assert identities.suppliers[elec_key] == ELEC_CH
    assert COTTON in identities.suppliers.values()
    tshirt = json.loads(
        (tmp_path / "processes" / f"{product_system.processes[0].id}.json").read_text(
            encoding="utf-8"
        )
    )
    electricity = next(
        e for e in tshirt["exchanges"] if "elec_per_kg" in (e.get("amountFormula") or "")
    )
    assert electricity["amountFormula"] == "cotton_tshirt__elec_per_kg * cotton_tshirt__fabric_mass"
    key = supplier_key(electricity["defaultProvider"]["@id"], electricity["flow"]["@id"])
    assert identities.suppliers[key] == ELEC_CH
    assert tshirt["location"]["@id"] == keygen("CH")
    parameters = [
        json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "parameters").glob("*.json")
    ]
    assert {p["name"] for p in parameters} == {
        "cotton_tshirt__fabric_mass",
        "cotton_tshirt__organic_share",
        "cotton_tshirt__waste_rate",
        "cotton_tshirt__elec_per_kg",
        "cotton_tshirt__fibre_mass",
    }
    derived = next(p for p in parameters if p["name"].endswith("fibre_mass"))
    assert derived["formula"] == "cotton_tshirt__fabric_mass * (1 + cotton_tshirt__waste_rate)"
    system = json.loads(
        next((tmp_path / "product_systems").glob("*.json")).read_text(encoding="utf-8")
    )
    assert [s["name"] for s in system["parameterSets"]] == ["small", "large"]
    assert system["parameterSets"][0]["parameters"][0]["name"] == "cotton_tshirt__fabric_mass"


def test_writer_rejects_unknown_units(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    odd = product_system.model_copy(deep=True)
    odd.processes[0].exchanges[1].unit = "furlong"
    with pytest.raises(NotSupported):
        write_jsonld(odd, tmp_path / "a", resolver)


def test_writer_names_a_foreground_input_whose_provider_is_missing(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    missing = product_system.model_copy(deep=True)
    missing.process("tshirt").exchanges[1].input = ForegroundRef(code="ghost")
    with pytest.raises(NotFound, match="ghost"):
        write_jsonld(missing, tmp_path / "a", resolver)


def test_writer_takes_the_reference_from_the_field_and_leaves_it_out_without_one(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    # fabric is no root: the t-shirt uses it
    named = product_system.model_copy(update={"reference_process": "fabric"})
    write_jsonld(named, tmp_path / "a", resolver)
    system = json.loads(
        next((tmp_path / "a" / "product_systems").glob("*.json")).read_text(encoding="utf-8")
    )
    assert system["refProcess"]["name"] == named.process("fabric").name
    assert system["targetAmount"] == 1.0
    unset = product_system.model_copy(update={"reference_process": None})
    write_jsonld(unset, tmp_path / "b", resolver)
    system = json.loads(
        next((tmp_path / "b" / "product_systems").glob("*.json")).read_text(encoding="utf-8")
    )
    assert "refProcess" not in system and len(system["processes"]) == 4


def test_writer_makes_natural_resources_inputs_and_emissions_outputs(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    write_jsonld(product_system, tmp_path, resolver)
    fabric = json.loads(
        (tmp_path / "processes" / f"{product_system.processes[1].id}.json").read_text(
            encoding="utf-8"
        )
    )
    river = next(e for e in fabric["exchanges"] if e["flow"]["name"] == "Water, river")
    assert river["isInput"] is True
    tshirt = json.loads(
        (tmp_path / "processes" / f"{product_system.processes[0].id}.json").read_text(
            encoding="utf-8"
        )
    )
    co2 = next(e for e in tshirt["exchanges"] if e["flow"]["name"] == "Carbon dioxide, fossil")
    assert co2["isInput"] is False


def test_writer_places_an_indicator_flow_by_its_sub_compartment(tmp_path: Path) -> None:
    secondary = ElementaryFlowRef(database="bio", id="secondary")
    exported = ElementaryFlowRef(database="bio", id="exported")
    system = ProductSystem(
        id=uuid.uuid4(),
        name="indicators",
        database=Database(
            name="db", elementary_flows="bio", scheme="olca", version="1", system_model="unit"
        ),
        processes=[
            Process(
                id=uuid.uuid4(),
                code="mill",
                name="mill",
                unit="kilogram",
                location="GLO",
                reference_product="pulp",
                exchanges=[
                    Exchange(
                        id=uuid.uuid4(), type="production", name="pulp", amount=1.0, unit="kilogram"
                    ),
                    Exchange(
                        id=uuid.uuid4(),
                        type="elementary",
                        name="Secondary materials",
                        amount=0.2,
                        unit="kilogram",
                        input=secondary,
                    ),
                    Exchange(
                        id=uuid.uuid4(),
                        type="elementary",
                        name="Exported energy - heat",
                        amount=3.0,
                        unit="megajoule",
                        input=exported,
                    ),
                ],
            )
        ],
    )
    resolver = DictResolver(
        {},
        {
            "secondary": FlowInfo(
                name="Secondary materials",
                compartment="inventory indicator",
                sub_compartment="resource use",
                unit="kilogram",
                flow_type="inventory indicator",
            ),
            "exported": FlowInfo(
                name="Exported energy - heat",
                compartment="inventory indicator",
                sub_compartment="output flow",
                unit="megajoule",
                flow_type="inventory indicator",
            ),
        },
    )
    write_jsonld(system, tmp_path, resolver)
    mill = json.loads(
        (tmp_path / "processes" / f"{system.processes[0].id}.json").read_text(encoding="utf-8")
    )
    by_name = {e["flow"]["name"]: e["isInput"] for e in mill["exchanges"]}
    assert by_name["Secondary materials"] is True
    assert by_name["Exported energy - heat"] is False


def test_one_unit_group_lists_every_unit_of_its_quantity() -> None:
    table = UnitTable()
    kg, mass = table.refs("kilogram")
    g, same = table.refs("gram")
    assert mass.id == same.id and kg.id != g.id
    groups = [e for e in table.entities() if isinstance(e, o.UnitGroup)]
    assert len(groups) == 1
    units = {u.name: (u.conversion_factor, u.is_ref_unit) for u in groups[0].units or []}
    assert units == {"kg": (1.0, True), "g": (0.001, None)}


def test_a_unit_openlca_lacks_takes_ids_derived_from_its_names() -> None:
    table = UnitTable()
    unit, prop = table.refs("guest night")
    assert (unit.id, unit.name) == (keygen("unit", "guest night"), "guest night")
    assert prop.id == keygen("flow property", units.GUEST_NIGHTS)
    [group] = [e for e in table.entities() if isinstance(e, o.UnitGroup)]
    assert group.id == keygen("unit group", units.GUEST_NIGHTS)
    assert UnitTable().refs("guest night") == (unit, prop)


def test_a_unit_openlca_files_under_another_quantity_keeps_the_cores_group() -> None:
    # openLCA files Nm3 under volume; the core keeps normal volume apart from volume and
    # standard volume
    table = UnitTable()
    standard, standard_prop = table.refs("standard cubic meter")
    normal, normal_prop = table.refs("normal cubic meter")
    _, volume = table.refs("cubic meter")
    foot, feet = table.refs("cubic foot")
    assert (standard.id, standard.name) == (keygen("unit", "Sm3"), "Sm3")
    assert (normal.id, normal.name) == (keygen("unit", "Nm3"), "Nm3")
    assert standard_prop.id == keygen("flow property", units.STANDARD_VOLUME) != volume.id
    assert normal_prop.id == keygen("flow property", units.NORMAL_VOLUME)
    assert normal_prop.id not in {standard_prop.id, volume.id}
    listed = {
        g.name: [(u.name, u.is_ref_unit) for u in g.units or []]
        for g in table.entities()
        if isinstance(g, o.UnitGroup)
    }
    assert listed[units.STANDARD_VOLUME] == [("Sm3", True)]
    assert listed[units.NORMAL_VOLUME] == [("Nm3", True)]
    assert feet.id == volume.id and foot.id == keygen(
        "unit", units.by_name("cubic foot").symbols[0]
    )
