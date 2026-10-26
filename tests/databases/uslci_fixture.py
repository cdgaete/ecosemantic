"""A synthetic USLCI release and an IPCC-style method on top of it, with the numbers a probe, a
build and a scoring of it answer.

The inventory holds five processes and thirteen flows, and the method one method of two categories.
Every case the source has to take appears once, and both archives are written as openLCA exports
them: a directory entry per folder, a member under `bin/` that is no entity, and, in the inventory,
records whose booleans are absent when false. The build must carry those members and read those
flags as false.

- a single-product process, `widget`, whose reference is one kilogram of widget;
- a physically allocated two-product process, `steel`, giving `steel` and `slag` the shares 0.75
  and 0.25 of each exchange that is neither product's own output;
- a causally allocated two-product process, `refinery`, with a factor for every pair of a product
  and an exchange: `fuel` takes 0.9 of the carbon dioxide and `gas` 0.1;
- a waste treatment, `treatment`, whose reference is the kilogram of scrap it takes in;
- an exchange in a flow property that is not its flow's reference property: `Water, river` is a
  mass flow whose second property is volume at 0.001 m3 per kg, and `widget` takes 2 m3 of it
  under a lognormal and an `amountFormula` of `2`, so a build moves it to 2000 kg and scales the
  distribution and the formula by 1000;
- a uniform distribution whose minimum and maximum are both 0, on `steel`'s carbon dioxide, which
  the core cannot hold as a distribution;
- two exchanges of one flow, `widget`'s two of `pm10`, each carrying such a uniform, so the
  left-out list holds two rows of one flow in one process, keyed by each exchange's own id;
- a waste input that is not its process's reference, `widget`'s 0.5 kg of scrap, which the core
  cannot link to a treater;
- an input no process produces, the kilogram of `imported part` that `widget` and both datasets of
  `refinery` take in, which the core leaves unlinked and records as three cut-offs of two inputs;
- an exchange in `lb av`, `widget`'s 100 lb av of methane, where the inventory's own mass group
  defines the pound at 0.4535924 kg and the core's table at 0.45359237, so a build converts the
  exchange into kilograms with USLCI's factor: 100 x 0.4535924 = 45.35924 kg;
- a product declared in a unit other than its flow's reference unit and kept so: `distillery`
  produces one litre of `Ethanol, 85% in water`, a volume flow whose reference unit is the cubic
  metre, and the litre's factor is the core's, so the build keeps the litre;
- an avoided product, `widget`'s 2 kg of slag taken in with `isAvoidedProduct`, which the core
  negates: a credit against slag's own production;
- elementary flows of which one is used and characterised (carbon dioxide), one used and not
  characterised (methane), and one defined and unused (sulfur dioxide);
- two bridges among them, `Electricity Bridge; GRID` and `Electricity Bridge; NOWHERE`, each putting
  out one megajoule of `electricity` and taking the same megajoule in, the input naming its intended
  provider only inside its `description` as the Commons writes it,
  `{"comment": "", "defaultProvider.@id": "<process id>"}`: the first names `grid mix` of the third
  zip below, the second a process no zip holds. Neither input carries a `defaultProvider` field, and
  the two bridges are the only processes producing `electricity` here, so with this zip alone the
  core leaves both inputs unlinked as several processes produce the flow;
- access notices: `widget` and `steel` carry one in their documentation, `refinery` another, and
  `treatment`, `distillery` and the two bridges document none, so the notices are one text twice, a
  second once and no text four times;
- a method repeating two ids the inventory holds, carbon dioxide under another description, whose
  factors name the carbon dioxide and the water the inventory uses and a flow the inventory does
  not hold (`Nitrogen oxides`): every factor's unit is the `kg` of the method's own unit group,
  under an id the written unit group lacks for the two that name the inventory's flow property;
- a second category, `water use`, so that both categories score: it characterises the water the
  inventory uses, which is the exchange the build converts.

The score of one unit of every dataset, under each category, is the dataset's column of `A`
solved against a demand of one unit of its product, `A` holding each production on its diagonal
and each technosphere input negated in its provider's row, times the characterised direct
emissions:

- `widget`, 1 kg: 3 kg carbon dioxide of its own, plus 2 kg steel at 6, minus the 2 kg of slag it
  avoids at 2: 3 + 12 - 4 = 11;
- `steel`, 1 kg: 8 kg carbon dioxide times its 0.75 share = 6;
- `slag`, 1 kg: 8 kg carbon dioxide times its 0.25 share = 2;
- `fuel`, 3 kg: 10 kg carbon dioxide times its 0.9 causal share, over the 3 kg produced = 3;
- `gas`, 1 kg: 10 kg carbon dioxide times its 0.1 causal share, over the 1 kg produced = 1;
- `treatment`, 1 kg of scrap treated: 1 kg carbon dioxide over the production of -1 kg = -1;
- `distillery`, one litre of ethanol, which is 0.001 m3 and is scored per one unit of the flow's
  reference unit: 1 kg carbon dioxide over 0.001 m3 = 1000, the core's own score being 1 per litre;
- `Electricity Bridge; GRID` and `Electricity Bridge; NOWHERE`, 1 MJ: the bridge's input has no
  provider here, so the core drops it: 0 under both categories;
- under `water use` only `widget` scores: its 2 m3 of water are 2000 kg at 0.001 = 2, and every
  other dataset is 0. The methane's 45.35924 kg are characterised by no category.

The method characterises two of the three elementary flows the inventory uses, the carbon dioxide
and the water, and not the methane: 2.

`write_bridged` writes the repository the two bridges link to, as the Baseline's own export: `grid
mix` and `coal plant` each put out one megajoule of `electricity`, the first taking 2 kg of `Crude
oil` and emitting 10 kg of carbon dioxide, the second taking one short ton of `coal` and emitting
20 kg. The `electricity` flow's record there differs from the inventory's in its description, and
`coal` and `Crude oil` are flows only it holds. `Crude oil` is an elementary flow whose reference
property is energy and which declares mass at 0.02 MJ per kg, so the grid mix's 2 kg are 2 / 0.02 =
100 MJ; its unit group defines the short ton at 907.18 kg where the core's table holds 907.18474, so
the coal plant's one ton is 907.18 kg and 907.18474 would be the core's answer. Merged with the
inventory and the method the bundle holds nine processes, eleven datasets and six elementary flows,
and the two bridges' inputs are the only ones whose description names a provider: the grid's links
to `grid mix` and the second names a process no zip holds. The four datasets the third zip adds
score:

- `grid mix`, 1 MJ: 10 kg of carbon dioxide: 10;
- `coal plant`, 1 MJ: 20 kg of carbon dioxide, its 907.18 kg of coal having no producer and so
  dropped: 20;
- `Electricity Bridge; GRID`, 1 MJ: its megajoule is provided by `grid mix` through the description,
  which emits 10 kg a megajoule: 10;
- `Electricity Bridge; NOWHERE`, 1 MJ: its provider is no zip's, so the input is dropped: 0.

Every other dataset keeps the score it has above.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipWriter

NS = uuid.UUID("3b9f1c2d-5a6e-4f70-9a1b-2c3d4e5f6a7b")

INVENTORY_NAME = "uslci-inventory.zip"
METHOD_NAME = "ipcc-method.zip"
BRIDGED_NAME = "electricity.zip"
METHOD = "IPCC GWP"
CLIMATE = "climate change"
WATER_USE = "water use"

AIR = "Elementary flows/Emissions to air/unspecified"
RIVER = "Elementary flows/Resources/in water"
PRODUCTS = "Technosphere Flows/Products"
METALS = "Technosphere Flows/Metals"
SCRAP = "Waste Flows/Scrap"
ENERGY = "Technosphere Flows/Energy"
FUELS = "Technosphere Flows/Fuels"
RESERVES = "Elementary flows/Resources/in ground"
UNLINKED_CATEGORY = "Technosphere Flows"


def _id(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


GROUPS: dict[str, tuple[str, tuple[tuple[str, float, bool], ...]]] = {
    "mass": ("Units of mass", (("kg", 1.0, True), ("lb av", 0.4535924, False))),
    "volume": ("Units of volume", (("l", 0.001, False), ("m3", 1.0, True))),
    "energy": ("Units of energy", (("MJ", 1.0, True),)),
    "method mass": ("Units of mass", (("kg", 1.0, True), ("g", 0.001, False))),
}
PROPERTIES: dict[str, tuple[str, str]] = {
    "mass": ("Mass", "mass"),
    "volume": ("Volume", "volume"),
    "energy": ("Energy", "energy"),
    "method mass": ("Mass", "method mass"),
}
FLOWS: dict[str, tuple[str, o.FlowType, str, str]] = {
    "widget": ("widget", o.FlowType.PRODUCT_FLOW, PRODUCTS, "mass"),
    "steel": ("steel", o.FlowType.PRODUCT_FLOW, METALS, "mass"),
    "slag": ("slag", o.FlowType.PRODUCT_FLOW, METALS, "mass"),
    "fuel": ("fuel", o.FlowType.PRODUCT_FLOW, PRODUCTS, "mass"),
    "gas": ("gas", o.FlowType.PRODUCT_FLOW, PRODUCTS, "mass"),
    "part": ("imported part", o.FlowType.PRODUCT_FLOW, METALS, "mass"),
    "scrap": ("steel scrap", o.FlowType.WASTE_FLOW, SCRAP, "mass"),
    "co2": ("Carbon dioxide, fossil", o.FlowType.ELEMENTARY_FLOW, AIR, "mass"),
    "ch4": ("Methane, fossil", o.FlowType.ELEMENTARY_FLOW, AIR, "mass"),
    "water": ("Water, river", o.FlowType.ELEMENTARY_FLOW, RIVER, "mass"),
    "so2": ("Sulfur dioxide", o.FlowType.ELEMENTARY_FLOW, AIR, "mass"),
    "ethanol": ("Ethanol, 85% in water", o.FlowType.PRODUCT_FLOW, PRODUCTS, "volume"),
    "pm10": ("Particulate matter, < 10 µm", o.FlowType.ELEMENTARY_FLOW, AIR, "mass"),
    "electricity": ("electricity", o.FlowType.PRODUCT_FLOW, ENERGY, "energy"),
    "coal": ("coal", o.FlowType.PRODUCT_FLOW, FUELS, "mass"),
    "crude": ("Crude oil", o.FlowType.ELEMENTARY_FLOW, RESERVES, "energy"),
}
FLOW_NAMES: dict[str, str] = {key: flows[0] for key, flows in FLOWS.items()}
BRIDGED_ONLY = ("coal", "crude")
EXTRA_PROPERTIES: dict[str, tuple[str, float]] = {
    "water": ("volume", 0.001),
    "crude": ("mass", 0.02),
}
INVENTORY_RECORD = "the inventory's own record"
BASELINE_RECORD = "the baseline's own record"
NOX = "Nitrogen oxides"
DISCLAIMER = "NREL Data Use Disclaimer: use, copy, modify and distribute these data"
WARRANTY = "USLCI: no warranty of any kind is given"
PROCESSES: dict[str, str] = {
    key: _id("process", key) for key in ("widget", "steel", "refinery", "treatment", "distillery")
}
BRIDGED_PROCESSES: dict[str, str] = {
    key: _id("bridged process", key) for key in ("grid mix", "coal plant")
}
BRIDGES: dict[str, str] = {
    name: _id("bridge", name)
    for name in ("Electricity Bridge; GRID", "Electricity Bridge; NOWHERE")
}
PROCESS_IDS: dict[str, str] = {**PROCESSES, **BRIDGED_PROCESSES, **BRIDGES}
CODES: dict[str, str] = {
    "widget": f"{PROCESSES['widget']}_{_id('flow', 'widget')}",
    "steel": f"{PROCESSES['steel']}_{_id('flow', 'steel')}",
    "slag": f"{PROCESSES['steel']}_{_id('flow', 'slag')}",
    "fuel": f"{PROCESSES['refinery']}_{_id('flow', 'fuel')}",
    "gas": f"{PROCESSES['refinery']}_{_id('flow', 'gas')}",
    "treatment": f"{PROCESSES['treatment']}_{_id('flow', 'scrap')}",
    "distillery": f"{PROCESSES['distillery']}_{_id('flow', 'ethanol')}",
    "Electricity Bridge; GRID": (
        f"{BRIDGES['Electricity Bridge; GRID']}_{_id('flow', 'electricity')}"
    ),
    "Electricity Bridge; NOWHERE": (
        f"{BRIDGES['Electricity Bridge; NOWHERE']}_{_id('flow', 'electricity')}"
    ),
}

EXPECTED: dict[str, object] = {
    "schema_versions": {INVENTORY_NAME: 3, METHOD_NAME: 2},
    "processes": 7,
    "elementary_flows": 5,
    "methods": 1,
    "categories": 2,
    "characterised": {METHOD: 2},
    "unknown_units": {},
    "other_property": 1,
    "refused": {
        "minimum must be less than maximum": 3,
        "a waste input that is not its process's reference": 1,
    },
    "unlinked_by_category": {UNLINKED_CATEGORY: 4},
    "build_refused": None,
    "bundle": {
        "datasets": 9,
        "elementary_flows": 5,
        "methods": 1,
        "categories": 2,
        "converted": 1,
    },
    "converted": {
        "amount": 2000.0,
        "geom_mean": 2000.0,
        "geom_sd": 1.2,
        "formula": "(2) * 1000.0",
    },
    "left_out": (
        {
            "process": "steel",
            "exchange": 3,
            "flow": "co2",
            "what": "distribution",
            "reason": "minimum must be less than maximum",
        },
        {
            "process": "widget",
            "exchange": 7,
            "flow": "scrap",
            "what": "exchange",
            "reason": "a waste input that is not its process's reference",
        },
        {
            "process": "widget",
            "exchange": 9,
            "flow": "pm10",
            "what": "distribution",
            "reason": "minimum must be less than maximum",
        },
        {
            "process": "widget",
            "exchange": 10,
            "flow": "pm10",
            "what": "distribution",
            "reason": "minimum must be less than maximum",
        },
    ),
    "notices": (
        (None, 4),
        (DISCLAIMER, 2),
        (WARRANTY, 1),
    ),
    "unlinked": (
        {"process": "widget", "flow": "part", "provider": None},
        {"process": "refinery", "flow": "part", "provider": None},
        {"process": "Electricity Bridge; GRID", "flow": "electricity", "provider": None},
        {"process": "Electricity Bridge; NOWHERE", "flow": "electricity", "provider": None},
    ),
    "unit_factors_differ": {"lb av": 1},
    "methane": {"amount": 45.35924, "unit": "kg"},
    "scores": {
        "widget": {CLIMATE: 11.0, WATER_USE: 2.0},
        "steel": {CLIMATE: 6.0, WATER_USE: 0.0},
        "slag": {CLIMATE: 2.0, WATER_USE: 0.0},
        "fuel": {CLIMATE: 3.0, WATER_USE: 0.0},
        "gas": {CLIMATE: 1.0, WATER_USE: 0.0},
        "treatment": {CLIMATE: -1.0, WATER_USE: 0.0},
        "distillery": {CLIMATE: 1000.0, WATER_USE: 0.0},
        "Electricity Bridge; GRID": {CLIMATE: 0.0, WATER_USE: 0.0},
        "Electricity Bridge; NOWHERE": {CLIMATE: 0.0, WATER_USE: 0.0},
    },
    "bridged": {
        "processes": 9,
        "datasets": 11,
        "elementary_flows": 6,
        "converted": 2,
        "unit_converted": {"lb av": 1, "sh tn": 1},
        "bridges_linked": 1,
        "bridges_unlinked": 1,
        "coal": {"amount": 907.18, "unit": "kg"},
        "crude": {"amount": 100.0, "unit": "MJ", "property": "Energy"},
        "scores": {
            "grid mix": {CLIMATE: 10.0, WATER_USE: 0.0},
            "coal plant": {CLIMATE: 20.0, WATER_USE: 0.0},
            "Electricity Bridge; GRID": {CLIMATE: 10.0, WATER_USE: 0.0},
            "Electricity Bridge; NOWHERE": {CLIMATE: 0.0, WATER_USE: 0.0},
        },
    },
}


def _unit(group: str, symbol: str) -> str:
    return _id(f"unit {group}", symbol)


def _group_id(key: str) -> str:
    return _id("group", key)


def _property_id(key: str) -> str:
    return _id("property", key)


def _flow_id(key: str) -> str:
    return _id("flow", key)


BRIDGED_CODES: dict[str, str] = {
    "grid mix": f"{BRIDGED_PROCESSES['grid mix']}_{_flow_id('electricity')}",
    "coal plant": f"{BRIDGED_PROCESSES['coal plant']}_{_flow_id('electricity')}",
}


def _ref(kind: o.RefType, entity_id: str, name: str) -> o.Ref:
    return o.Ref(id=entity_id, name=name, ref_type=kind)


def _unit_ref(group: str, symbol: str) -> o.Ref:
    return _ref(o.RefType.Unit, _unit(group, symbol), symbol)


def _property_ref(key: str) -> o.Ref:
    return _ref(o.RefType.FlowProperty, _property_id(key), PROPERTIES[key][0])


def _flow_ref(key: str) -> o.Ref:
    name, flow_type, _, _ = FLOWS[key]
    return o.Ref(id=_flow_id(key), name=name, ref_type=o.RefType.Flow, flow_type=flow_type)


def _nox_ref() -> o.Ref:
    return o.Ref(
        id=_flow_id("nox"),
        name=NOX,
        ref_type=o.RefType.Flow,
        flow_type=o.FlowType.ELEMENTARY_FLOW,
    )


def _exchange(
    n: int,
    key: str,
    amount: float,
    *,
    is_input: bool,
    unit: str | None = None,
    reference: bool = False,
    provider: str | None = None,
    avoided: bool = False,
    flow_property: str | None = None,
    uncertainty: o.Uncertainty | None = None,
    formula: str | None = None,
    description: str | None = None,
) -> o.Exchange:
    _, _, _, reference_property = FLOWS[key]
    given = flow_property if flow_property is not None else reference_property
    group = PROPERTIES[given][1]
    symbol = unit if unit is not None else GROUPS[group][1][0][0]
    return o.Exchange(
        internal_id=n,
        flow=_flow_ref(key),
        flow_property=_property_ref(given),
        unit=_unit_ref(group, symbol),
        amount=amount,
        amount_formula=formula,
        is_input=is_input,
        is_quantitative_reference=reference,
        is_avoided_product=avoided,
        default_provider=(
            _ref(o.RefType.Process, provider, provider) if provider is not None else None
        ),
        uncertainty=uncertainty,
        description=description,
    )


def _named_process(
    entity_id: str, name: str, exchanges: list[o.Exchange], *, at: str = "GLO", **extra: object
) -> o.Process:
    """A unit process at the location `at` codes, holding the exchanges a case gives it."""
    return o.Process(
        id=entity_id,
        name=name,
        process_type=o.ProcessType.UNIT_PROCESS,
        location=_ref(o.RefType.Location, _id("location", at), at),
        exchanges=exchanges,
        last_internal_id=len(exchanges),
        **extra,
    )


def _process(key: str, exchanges: list[o.Exchange], **extra: object) -> o.Process:
    return _named_process(PROCESSES[key], key, exchanges, **extra)


def _described(provider_id: str) -> str:
    """The description the Commons writes on a bridge input, naming the process it is meant to link
    to."""
    return json.dumps({"comment": "", "defaultProvider.@id": provider_id})


def _bridge(name: str, provider_id: str, *, description: str | None = None) -> o.Process:
    """A bridge process: one megajoule of electricity out and one in, the input naming its intended
    provider only in its description; `description` writes another text there."""
    return _named_process(
        BRIDGES[name],
        name,
        [
            _exchange(1, "electricity", 1.0, is_input=False, reference=True),
            _exchange(
                2,
                "electricity",
                1.0,
                is_input=True,
                description=_described(provider_id) if description is None else description,
            ),
        ],
    )


def _noticed(text: str) -> dict[str, object]:
    """The documentation a process carries, holding one access notice."""
    return {"process_documentation": o.ProcessDocumentation(restrictions_description=text)}


def _physical(key: str, value: float) -> o.AllocationFactor:
    return o.AllocationFactor(
        allocation_type=o.AllocationType.PHYSICAL_ALLOCATION, product=_flow_ref(key), value=value
    )


def _causal(key: str, exchange: int, value: float) -> o.AllocationFactor:
    return o.AllocationFactor(
        allocation_type=o.AllocationType.CAUSAL_ALLOCATION,
        product=_flow_ref(key),
        exchange=o.ExchangeRef(internal_id=exchange),
        value=value,
    )


def _factor(flow: o.Ref, property_key: str, value: float) -> o.ImpactFactor:
    return o.ImpactFactor(
        flow=flow,
        flow_property=_property_ref(property_key),
        unit=_unit_ref("method mass", "kg"),
        value=value,
    )


def _dropped(value: object) -> object:
    """A record as openLCA writes it: every boolean a record leaves false is absent."""
    if isinstance(value, dict):
        return {key: _dropped(item) for key, item in value.items() if item is not False}
    if isinstance(value, list):
        return [_dropped(item) for item in value]
    return value


def _postprocessed(path: Path, version: int, *, flags: bool) -> Path:
    """Rebuild the archive as openLCA exports one: `openlca.json`, a directory entry per folder, a
    member under `bin/` that is no entity, and, when `flags` is set, no boolean left false."""
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    folders = sorted({name.split("/", 1)[0] for name in members if "/" in name})
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("openlca.json", json.dumps({"schemaVersion": version}))
        for name, content in members.items():
            if name == "openlca.json":
                continue
            if flags and name.endswith(".json"):
                content = json.dumps(_dropped(json.loads(content))).encode()
            archive.writestr(name, content)
        for folder in folders:
            if folder != "bin":
                archive.writestr(f"{folder}/", b"")
        archive.writestr(
            f"bin/processes/{_id('process', 'widget')}/calculation-preferences.json",
            json.dumps({"impactMethod": "IPCC", "assignment": "PHYSICAL_ALLOCATION"}).encode(),
        )
    return path


def _definitions(writer: ZipWriter, *, odd_unit: bool = False, short_ton: bool = False) -> None:
    """The unit groups and flow properties every zip carries; `odd_unit` gives the mass group a unit
    the core's table lacks, which the methane is then measured in, and `short_ton` the short ton the
    bridged repository defines at 907.18 kg."""
    for key, (name, units) in GROUPS.items():
        if odd_unit and key == "mass":
            units = (*units, ("furlong", 1.0, False))
        if short_ton and key == "mass":
            units = (*units, ("sh tn", 907.18, False))
        writer.write(
            o.UnitGroup(
                id=_group_id(key),
                name=name,
                units=[
                    o.Unit(
                        id=_unit(key, symbol),
                        name=symbol,
                        conversion_factor=factor,
                        is_ref_unit=reference,
                    )
                    for symbol, factor, reference in units
                ],
            )
        )
    for key, (name, group) in PROPERTIES.items():
        writer.write(
            o.FlowProperty(
                id=_property_id(key),
                name=name,
                flow_property_type=o.FlowPropertyType.PHYSICAL_QUANTITY,
                unit_group=_ref(o.RefType.UnitGroup, _group_id(group), GROUPS[group][0]),
            )
        )


def _absent() -> o.Exchange:
    """An input naming a flow the archive does not hold."""
    return o.Exchange(
        internal_id=9,
        flow=o.Ref(
            id=_flow_id("absent"),
            name="absent",
            ref_type=o.RefType.Flow,
            flow_type=o.FlowType.PRODUCT_FLOW,
        ),
        flow_property=_property_ref("mass"),
        unit=_unit_ref("mass", "kg"),
        amount=1.0,
        is_input=True,
    )


def _flow_record(key: str, *, description: str | None = None) -> o.Flow:
    """A flow of the fixture's tables, in its reference property and, where it declares one, in the
    second property `EXTRA_PROPERTIES` gives it."""
    name, flow_type, category, reference_property = FLOWS[key]
    properties = [
        o.FlowPropertyFactor(
            flow_property=_property_ref(reference_property),
            conversion_factor=1.0,
            is_ref_flow_property=True,
        )
    ]
    extra = EXTRA_PROPERTIES.get(key)
    if extra is not None:
        properties.append(
            o.FlowPropertyFactor(
                flow_property=_property_ref(extra[0]),
                conversion_factor=extra[1],
                is_ref_flow_property=False,
            )
        )
    return o.Flow(
        id=_flow_id(key),
        name=name,
        flow_type=flow_type,
        category=category,
        description=description,
        cas="124-38-9" if key == "co2" else None,
        flow_properties=properties,
    )


def write_inventory(
    path: Path,
    *,
    odd_unit: bool = False,
    bare_conversion: bool = False,
    dangling_flow: bool = False,
    grid_description: str | None = None,
) -> Path:
    """Write the synthetic inventory as a schema-3 zip at path and return it. The methane takes
    its unit under a symbol the core's table lacks when `odd_unit` is set; the water is given in
    volume with neither a distribution nor a formula when `bare_conversion` is set; the widget
    takes in a flow the archive does not hold when `dangling_flow` is set; the grid bridge's input
    carries the description `grid_description` gives it, and the one the Commons writes when it is
    not given. The flows only the bridged repository holds are not written here."""
    with ZipWriter(str(path)) as writer:
        _definitions(writer, odd_unit=odd_unit)
        writer.write(o.Location(id=_id("location", "GLO"), name="Global", code="GLO"))
        for key in FLOWS:
            if key in BRIDGED_ONLY:
                continue
            writer.write(
                _flow_record(key, description=INVENTORY_RECORD if key == "electricity" else None)
            )
        lognormal = o.Uncertainty(
            distribution_type=o.UncertaintyType.LOG_NORMAL_DISTRIBUTION, geom_mean=2.0, geom_sd=1.2
        )
        degenerate = o.Uncertainty(
            distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION, minimum=0.0, maximum=0.0
        )
        widget = [
            _exchange(1, "widget", 1.0, is_input=False, reference=True),
            _exchange(2, "steel", 2.0, is_input=True, provider=PROCESSES["steel"]),
            _exchange(3, "slag", 2.0, is_input=True, provider=PROCESSES["steel"], avoided=True),
            _exchange(
                4,
                "water",
                2.0,
                is_input=True,
                unit="m3",
                flow_property="volume",
                uncertainty=None if bare_conversion else lognormal,
                formula=None if bare_conversion else "2",
            ),
            _exchange(5, "co2", 3.0, is_input=False),
            _exchange(6, "ch4", 100.0, is_input=False, unit="furlong" if odd_unit else "lb av"),
            _exchange(7, "scrap", 0.5, is_input=True, provider=PROCESSES["treatment"]),
            _exchange(8, "part", 1.0, is_input=True),
            _exchange(9, "pm10", 1.0, is_input=False, uncertainty=degenerate),
            _exchange(10, "pm10", 1.0, is_input=False, uncertainty=degenerate),
        ]
        if dangling_flow:
            widget.append(_absent())
        writer.write(_process("widget", widget, **_noticed(DISCLAIMER)))
        writer.write(
            _process(
                "steel",
                [
                    _exchange(1, "steel", 1.0, is_input=False, reference=True),
                    _exchange(2, "slag", 1.0, is_input=False),
                    _exchange(3, "co2", 8.0, is_input=False, uncertainty=degenerate),
                ],
                default_allocation_method=o.AllocationType.PHYSICAL_ALLOCATION,
                allocation_factors=[_physical("steel", 0.75), _physical("slag", 0.25)],
                **_noticed(DISCLAIMER),
            )
        )
        writer.write(
            _process(
                "refinery",
                [
                    _exchange(1, "fuel", 3.0, is_input=False, reference=True),
                    _exchange(2, "gas", 1.0, is_input=False),
                    _exchange(3, "co2", 10.0, is_input=False),
                    _exchange(4, "part", 1.0, is_input=True),
                ],
                default_allocation_method=o.AllocationType.CAUSAL_ALLOCATION,
                allocation_factors=[
                    _causal("fuel", 3, 0.9),
                    _causal("gas", 3, 0.1),
                    _causal("fuel", 4, 0.5),
                    _causal("gas", 4, 0.5),
                ],
                **_noticed(WARRANTY),
            )
        )
        writer.write(
            _process(
                "treatment",
                [
                    _exchange(1, "scrap", 1.0, is_input=True, reference=True),
                    _exchange(2, "co2", 1.0, is_input=False),
                ],
            )
        )
        writer.write(
            _process(
                "distillery",
                [
                    _exchange(1, "ethanol", 1.0, is_input=False, reference=True, unit="l"),
                    _exchange(2, "co2", 1.0, is_input=False),
                ],
            )
        )
        writer.write(
            _bridge(
                "Electricity Bridge; GRID",
                BRIDGED_PROCESSES["grid mix"],
                description=grid_description,
            )
        )
        writer.write(_bridge("Electricity Bridge; NOWHERE", _id("bridged process", "absent")))
    return _postprocessed(path, 3, flags=True)


def write_bridged(path: Path) -> Path:
    """Write the repository USLCI's bridges link to as a schema-2 zip at path and return it: two
    producers of `electricity`, its own `electricity` record, the `coal` and `crude oil` flows only
    it holds, a location only it holds, a unit group defining `sh tn` at 907.18 kg, and two
    producers that emit carbon dioxide."""
    with ZipWriter(str(path)) as writer:
        _definitions(writer, short_ton=True)
        writer.write(o.Location(id=_id("location", "GLO"), name="Global", code="GLO"))
        writer.write(o.Location(id=_id("location", "US"), name="United States", code="US"))
        for key in ("electricity", "coal", "crude"):
            writer.write(
                _flow_record(key, description=BASELINE_RECORD if key == "electricity" else None)
            )
        writer.write(
            _named_process(
                BRIDGED_PROCESSES["grid mix"],
                "grid mix",
                [
                    _exchange(1, "electricity", 1.0, is_input=False, reference=True),
                    _exchange(2, "crude", 2.0, is_input=True, unit="kg", flow_property="mass"),
                    _exchange(3, "co2", 10.0, is_input=False),
                ],
            )
        )
        writer.write(
            _named_process(
                BRIDGED_PROCESSES["coal plant"],
                "coal plant",
                [
                    _exchange(1, "electricity", 1.0, is_input=False, reference=True),
                    _exchange(2, "coal", 1.0, is_input=True, unit="sh tn"),
                    _exchange(3, "co2", 20.0, is_input=False),
                ],
                at="US",
            )
        )
    return _postprocessed(path, 2, flags=False)


def write_method(
    path: Path, *, stray_property: bool = False, dangling_category: bool = False
) -> Path:
    """Write the synthetic method as a schema-2 zip at path and return it. A factor whose flow
    property its written flow does not carry is what `stray_property` writes; a method naming a
    category the package does not hold is what `dangling_category` writes."""
    with ZipWriter(str(path)) as writer:
        _definitions(writer)
        for key in ("co2", "nox"):
            writer.write(
                o.Flow(
                    id=_flow_id(key),
                    name=FLOWS[key][0] if key in FLOWS else NOX,
                    description="the method's own record",
                    flow_type=o.FlowType.ELEMENTARY_FLOW,
                    category=AIR,
                    flow_properties=[
                        o.FlowPropertyFactor(
                            flow_property=_property_ref("method mass"),
                            conversion_factor=1.0,
                            is_ref_flow_property=True,
                        )
                    ],
                )
            )
        climate = o.ImpactCategory(
            id=_id("category", CLIMATE),
            name=CLIMATE,
            ref_unit="kg CO2-Eq",
            impact_factors=[
                _factor(_flow_ref("co2"), "volume" if stray_property else "mass", 1.0),
                _factor(_nox_ref(), "method mass", 2.0),
            ],
        )
        water = o.ImpactCategory(
            id=_id("category", WATER_USE),
            name=WATER_USE,
            ref_unit="kg",
            impact_factors=[_factor(_flow_ref("water"), "mass", 0.001)],
        )
        writer.write(climate)
        writer.write(water)
        named = [
            _ref(o.RefType.ImpactCategory, climate.id, climate.name),
            _ref(o.RefType.ImpactCategory, water.id, water.name),
        ]
        if dangling_category:
            named.append(_ref(o.RefType.ImpactCategory, _id("category", "absent"), "absent"))
        writer.write(o.ImpactMethod(id=_id("method", METHOD), name=METHOD, impact_categories=named))
    return _postprocessed(path, 2, flags=False)
