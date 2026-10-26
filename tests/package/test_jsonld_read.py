from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.package.jsonld import read_jsonld, write_jsonld
from ecosemantic.package.log import diff_product_systems
from ecosemantic.package.sidecar import ActivityRecord, Identities, ProjectRecord, Sidecar
from ecosemantic.ports.resolver import BackgroundInfo
from tests.conftest import (
    BACKGROUNDS,
    CO2,
    ELEC_CH,
    FLOWS,
    ex,
    label_system,
    tshirt_labelled,
)
from tests.dict_resolver import DictResolver


def _sidecar(product_system: ProductSystem, identities: Identities) -> Sidecar:
    return Sidecar(
        product_system=ProjectRecord(
            id=product_system.id,
            name=product_system.name,
            description=product_system.description,
            notes=product_system.notes,
            database=product_system.database,
            hash=content_hash(product_system),
            processes=[ActivityRecord(id=a.id, code=a.code) for a in product_system.processes],
        ),
        identities=identities,
        scenarios=product_system.scenarios,
        metadata={a.id: a.metadata for a in product_system.processes},
    )


def test_read_after_write_keeps_the_hash(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    sidecar = _sidecar(product_system, write_jsonld(product_system, tmp_path, resolver))
    back = read_jsonld(tmp_path, sidecar)
    assert content_hash(back) == content_hash(product_system)
    assert diff_product_systems(product_system, back) == []
    assert back.process("tshirt").exchanges[2].name == "sewing electricity"
    assert back.process("tshirt").metadata["life_cycle_stage"] == "manufacturing"


def test_the_reference_process_round_trips_through_the_package(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    named = product_system.model_copy(update={"reference_process": "fabric"})
    back = read_jsonld(
        tmp_path / "a", _sidecar(named, write_jsonld(named, tmp_path / "a", resolver))
    )
    assert back.reference_process == "fabric"
    unset = product_system.model_copy(update={"reference_process": None})
    back = read_jsonld(
        tmp_path / "b", _sidecar(unset, write_jsonld(unset, tmp_path / "b", resolver))
    )
    assert back.reference_process is None


def test_edits_made_in_the_files_come_back_as_changes(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    sidecar = _sidecar(product_system, write_jsonld(product_system, tmp_path, resolver))
    fabric = product_system.process("fabric")
    path = tmp_path / "processes" / f"{fabric.id}.json"
    data = json.loads(path.read_text())
    data["name"] = "cotton fabric, woven"
    for e in data["exchanges"]:
        if e["flow"]["name"] == "tap water":
            e["amount"] = 40.0
    co2 = json.loads((tmp_path / "flows" / f"{CO2.id}.json").read_text())
    data["exchanges"].append(
        {
            "@type": "Exchange",
            "internalId": 99,
            "amount": 0.002,
            "isInput": False,
            "flow": {
                "@type": "Flow",
                "@id": co2["@id"],
                "name": co2["name"],
                "flowType": "ELEMENTARY_FLOW",
            },
            "unit": data["exchanges"][0]["unit"],
            "flowProperty": data["exchanges"][0]["flowProperty"],
        }
    )
    path.write_text(json.dumps(data))
    prefix = sidecar.identities.parameter_prefix
    for p in (tmp_path / "parameters").glob("*.json"):
        param = json.loads(p.read_text())
        if param["name"] == prefix + "waste_rate":
            param["value"] = 0.12
            p.write_text(json.dumps(param))
    back = read_jsonld(tmp_path, sidecar)
    changes = {(c.op, c.entity, c.field) for c in diff_product_systems(product_system, back)}
    assert changes == {
        ("update", "process", "name"),
        ("update", "exchange", "amount"),
        ("add", "exchange", None),
        ("update", "parameter", "value"),
    }
    added = next(e for e in back.process("fabric").exchanges if e.amount == 0.002)
    assert added.type == "elementary" and added.input == CO2
    assert added.name == "Carbon dioxide, fossil"


def test_new_process_gets_a_fresh_activity(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    sidecar = _sidecar(product_system, write_jsonld(product_system, tmp_path, resolver))
    label_id = str(uuid.uuid4())
    tshirt_path = tmp_path / "processes" / f"{product_system.processes[0].id}.json"
    tshirt = json.loads(tshirt_path.read_text())
    unit = tshirt["exchanges"][0]["unit"]
    flow_property = tshirt["exchanges"][0]["flowProperty"]
    flow = {"@type": "Flow", "@id": str(uuid.uuid4()), "name": "label", "flowType": "PRODUCT_FLOW"}
    (tmp_path / "flows" / f"{flow['@id']}.json").write_text(
        json.dumps(
            {
                **flow,
                "flowProperties": [
                    {
                        "flowProperty": flow_property,
                        "conversionFactor": 1.0,
                        "isRefFlowProperty": True,
                    }
                ],
            }
        )
    )
    (tmp_path / "processes" / f"{label_id}.json").write_text(
        json.dumps(
            {
                "@type": "Process",
                "@id": label_id,
                "name": "label",
                "processType": "UNIT_PROCESS",
                "location": tshirt["location"],
                "exchanges": [
                    {
                        "@type": "Exchange",
                        "internalId": 1,
                        "amount": 1.0,
                        "isInput": False,
                        "isQuantitativeReference": True,
                        "flow": flow,
                        "unit": unit,
                        "flowProperty": flow_property,
                    }
                ],
            }
        )
    )
    tshirt["exchanges"].append(
        {
            "@type": "Exchange",
            "internalId": 77,
            "amount": 1.0,
            "isInput": True,
            "flow": flow,
            "defaultProvider": {"@type": "Process", "@id": label_id, "name": "label"},
            "unit": unit,
            "flowProperty": flow_property,
        }
    )
    tshirt_path.write_text(json.dumps(tshirt))
    back = read_jsonld(tmp_path, sidecar)
    assert back.process("label").reference_product == "label"
    assert back.process("tshirt").exchanges[-1].input.code == "label"
    assert {c.op for c in diff_product_systems(product_system, back)} == {"add"}


def test_a_parameter_set_taking_a_scenario_s_name_is_invalid(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    sidecar = _sidecar(product_system, write_jsonld(product_system, tmp_path, resolver))
    path = tmp_path / "product_systems" / f"{product_system.id}.json"
    document = json.loads(path.read_text())
    document["parameterSets"].append({"@type": "ParameterRedefSet", "name": "organic"})
    path.write_text(json.dumps(document))
    with pytest.raises(Invalid, match=r"cases and scenarios share the names \['organic'\]"):
        read_jsonld(tmp_path, sidecar)


def _transport_flagged(
    product_system: ProductSystem, resolver: DictResolver, root: Path, flags: dict[str, object]
) -> Sidecar:
    """The t-shirt's package with its transport input's exchange carrying openLCA's direction
    flags; a `flowType` among them goes on the flow, in the exchange and in its own file."""
    sidecar = _sidecar(product_system, write_jsonld(product_system, root, resolver))
    path = root / "processes" / f"{product_system.process('tshirt').id}.json"
    document = json.loads(path.read_text())
    transport = next(e for e in document["exchanges"] if e["amount"] == 0.0005)
    flow_type = flags.pop("flowType", None)
    transport.update(flags)
    if flow_type is not None:
        transport["flow"]["flowType"] = flow_type
        flow_path = root / "flows" / f"{transport['flow']['@id']}.json"
        flow = json.loads(flow_path.read_text())
        flow["flowType"] = flow_type
        flow_path.write_text(json.dumps(flow))
    path.write_text(json.dumps(document))
    return sidecar


@pytest.mark.parametrize(
    "flags",
    [
        {"isInput": False, "flowType": "WASTE_FLOW"},
        {"isInput": False, "isAvoidedProduct": True},
    ],
    ids=["waste-output", "avoided-product"],
)
def test_a_waste_output_or_an_avoided_product_reads_as_a_negated_product_exchange(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path, flags: dict[str, object]
) -> None:
    sidecar = _transport_flagged(product_system, resolver, tmp_path, flags)
    back = read_jsonld(tmp_path, sidecar)
    stated = product_system.process("tshirt").exchanges[3]
    read = back.process("tshirt").exchanges[3]
    assert (read.type, read.amount, read.input) == ("product", -0.0005, stated.input)
    assert stated.uncertainty is not None and read.uncertainty is not None
    negated = stated.uncertainty.scaled(-1.0).params
    assert read.uncertainty.params["negative"] is True and negated["negative"] is True
    # the scale crosses exp and log on the way through openLCA's geometric deviation
    assert read.uncertainty.params["scale"] == pytest.approx(negated["scale"])
    assert read.uncertainty.params["loc"] == pytest.approx(negated["loc"])


def test_a_product_output_neither_reference_nor_avoided_is_refused_as_a_co_product(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    sidecar = _transport_flagged(product_system, resolver, tmp_path, {"isInput": False})
    with pytest.raises(Invalid, match="of 'cotton t-shirt, assembled' is a co-product"):
        read_jsonld(tmp_path, sidecar)


def test_a_negative_input_reads_back_as_written(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    negative = product_system.model_copy(deep=True)
    transport = negative.process("tshirt").exchanges[3]
    transport.amount = -0.0005
    assert transport.uncertainty is not None
    transport.uncertainty = transport.uncertainty.scaled(-1.0)
    sidecar = _sidecar(negative, write_jsonld(negative, tmp_path, resolver))
    back = read_jsonld(tmp_path, sidecar)
    read = back.process("tshirt").exchanges[3]
    assert (read.type, read.amount, read.input) == ("product", -0.0005, transport.input)
    assert read.uncertainty is not None and read.uncertainty.params["negative"] is True
    # the scale crosses exp and log on the way through openLCA's geometric deviation
    assert read.uncertainty.params["scale"] == pytest.approx(0.3)
    assert content_hash(back) == content_hash(negative)


def test_an_empty_document_round_trips(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    empty = product_system.model_copy(
        deep=True,
        update={
            "processes": [],
            "parameters": [],
            "cases": [],
            "scenarios": [],
            "reference_process": None,
        },
    )
    sidecar = _sidecar(empty, write_jsonld(empty, tmp_path, resolver))
    back = read_jsonld(tmp_path, sidecar)
    assert back.processes == [] and content_hash(back) == content_hash(empty)


def test_a_link_round_trips_as_a_product_system_provider(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    label = label_system()
    label = label.model_copy(update={"hash": content_hash(label)})
    labelled = tshirt_labelled(product_system, label)
    identities = write_jsonld(labelled, tmp_path, resolver, linked={label.id: label})
    system = json.loads(next((tmp_path / "product_systems").glob("*.json")).read_text())
    [provider] = [
        link["provider"]
        for link in system["processLinks"]
        if link["provider"]["@type"] == "ProductSystem"
    ]
    assert provider["@id"] == str(label.id)
    back = read_jsonld(tmp_path, _sidecar(labelled, identities))
    assert (
        back.process("tshirt").exchanges[-1].input == labelled.process("tshirt").exchanges[-1].input
    )
    assert content_hash(back) == content_hash(labelled)


def test_a_write_not_given_a_linked_system_names_the_link(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    label = label_system()
    with pytest.raises(NotFound, match=str(label.id)):
        write_jsonld(tshirt_labelled(product_system, label), tmp_path, resolver)


WIND_CH = BackgroundRef(
    database=ELEC_CH.database,
    id="0b1f2c3d-4e5f-5a6b-8c7d-9e0f1a2b3c4d_" + ELEC_CH.id.split("_")[1],
)


def test_two_suppliers_of_one_product_keep_their_own_supplier(
    product_system: ProductSystem, tmp_path: Path
) -> None:
    resolver = DictResolver(
        {
            **BACKGROUNDS,
            WIND_CH.id: BackgroundInfo(
                name="electricity production, wind",
                reference_product="electricity, medium voltage",
                location="CH",
                unit="kilowatt hour",
            ),
        },
        FLOWS,
    )
    tshirt = product_system.process("tshirt")
    yarn = product_system.process("yarn")
    # one wind input beside the grid input of the same process, one in a process without it
    tshirt.exchanges.append(
        ex("tshirt", 9, "product", "wind electricity", 0.5, "kilowatt hour", WIND_CH)
    )
    yarn.exchanges.append(
        ex("yarn", 9, "product", "wind electricity", 0.7, "kilowatt hour", WIND_CH)
    )
    sidecar = _sidecar(product_system, write_jsonld(product_system, tmp_path, resolver))
    back = read_jsonld(tmp_path, sidecar)
    assert content_hash(back) == content_hash(product_system)
    inputs = {(p.code, e.name): e.input for p in back.processes for e in p.exchanges}
    assert inputs[("tshirt", "wind electricity")] == WIND_CH
    assert inputs[("yarn", "wind electricity")] == WIND_CH
    assert inputs[("fabric", "weaving electricity")] == ELEC_CH
