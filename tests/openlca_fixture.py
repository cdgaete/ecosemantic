"""A synthetic openLCA package: five processes, one multi-output, a waste chain, two methods."""

from __future__ import annotations

import uuid
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipWriter

NS = uuid.UUID("7d1a2b3c-4e5f-4a6b-8c7d-9e0f1a2b3c4d")
NAME = "fixture-olca"


def _id(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


GROUPS: dict[str, tuple[str, list[tuple[str, float]]]] = {
    "mass": ("kg", [("g", 0.001)]),
    "energy": ("MJ", [("kWh", 3.6)]),
    "volume": ("m3", []),
    "items": ("Item(s)", []),
}
PROPERTIES = {"Mass": "mass", "Energy": "energy", "Volume": "volume", "Number of items": "items"}
AIR = "Elementary flows/Emissions to air/unspecified"
FLOWS: dict[str, tuple[str, str, o.FlowType, str | None]] = {
    "electricity": ("electricity, medium voltage", "Energy", o.FlowType.PRODUCT_FLOW, None),
    "steel": ("steel, low-alloyed", "Mass", o.FlowType.PRODUCT_FLOW, None),
    "fuel": ("fuel oil", "Mass", o.FlowType.PRODUCT_FLOW, None),
    "gas": ("refinery gas", "Mass", o.FlowType.PRODUCT_FLOW, None),
    "widget": ("widget", "Number of items", o.FlowType.PRODUCT_FLOW, None),
    "part": ("imported part", "Mass", o.FlowType.PRODUCT_FLOW, None),
    "scrap": ("steel scrap", "Mass", o.FlowType.WASTE_FLOW, None),
    "co2": ("Carbon dioxide, fossil", "Mass", o.FlowType.ELEMENTARY_FLOW, AIR),
    "ch4": ("Methane, fossil", "Mass", o.FlowType.ELEMENTARY_FLOW, AIR),
    "water": (
        "Water, river",
        "Volume",
        o.FlowType.ELEMENTARY_FLOW,
        "Elementary flows/Resources/in water",
    ),
}
PROCESSES = {
    key: _id("process", key) for key in ("elec", "steel", "refinery", "widget", "treatment")
}
FLOW_IDS = {key: _id("flow", key) for key in FLOWS}
MISSING_PROVIDER = _id("process", "missing")
MISSING_LOCATION = _id("location", "missing")
METHOD = "fixture method"
LOCATIONS = {"CL": "Chile"}
WIDGET_CLIMATE = 8.62
WIDGET_WATER = 0.02


def _ref(kind: o.RefType, entity_id: str, name: str) -> o.Ref:
    return o.Ref(id=entity_id, name=name, ref_type=kind)


def _unit_ref(symbol: str) -> o.Ref:
    return _ref(o.RefType.Unit, _id("unit", symbol), symbol)


def _property_ref(name: str) -> o.Ref:
    return _ref(o.RefType.FlowProperty, _id("property", name), name)


def _flow_ref(key: str) -> o.Ref:
    name, _, flow_type, _ = FLOWS[key]
    return o.Ref(id=FLOW_IDS[key], name=name, ref_type=o.RefType.Flow, flow_type=flow_type)


def _location_ref(code: str) -> o.Ref:
    """A ref to the location record the package carries under code."""
    return _ref(o.RefType.Location, _id("location", code), LOCATIONS[code])


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
    uncertainty: o.Uncertainty | None = None,
    prop: str | None = None,
) -> o.Exchange:
    _, flow_property, _, _ = FLOWS[key]
    symbol = unit if unit is not None else GROUPS[PROPERTIES[flow_property]][0]
    return o.Exchange(
        internal_id=n,
        flow=_flow_ref(key),
        flow_property=_property_ref(prop if prop is not None else flow_property),
        unit=_unit_ref(symbol),
        amount=amount,
        is_input=is_input,
        is_quantitative_reference=reference,
        is_avoided_product=avoided,
        default_provider=(
            o.Ref(id=provider, name=provider, ref_type=o.RefType.Process) if provider else None
        ),
        uncertainty=uncertainty,
    )


def _process(
    key: str,
    exchanges: list[o.Exchange],
    location: str | None = "GLO",
    location_id: str | None = None,
    **extra: object,
) -> o.Process:
    return o.Process(
        id=PROCESSES[key],
        name=f"{key} production",
        process_type=o.ProcessType.UNIT_PROCESS,
        location=(
            _ref(o.RefType.Location, location_id or _id("location", location), "Global")
            if location is not None
            else None
        ),
        exchanges=exchanges,
        last_internal_id=len(exchanges),
        **extra,
    )


def _factor(key: str, value: float) -> o.AllocationFactor:
    return o.AllocationFactor(
        allocation_type=o.AllocationType.PHYSICAL_ALLOCATION, product=_flow_ref(key), value=value
    )


def _causal_factor(key: str, exchange: int, value: float) -> o.AllocationFactor:
    return o.AllocationFactor(
        allocation_type=o.AllocationType.CAUSAL_ALLOCATION,
        product=_flow_ref(key),
        exchange=o.ExchangeRef(internal_id=exchange),
        value=value,
    )


def _impact(
    key: str, prop: str, symbol: str, value: float, location: str | None = None
) -> o.ImpactFactor:
    return o.ImpactFactor(
        flow=_flow_ref(key),
        flow_property=_property_ref(prop),
        unit=_unit_ref(symbol),
        value=value,
        location=_location_ref(location) if location is not None else None,
    )


def build_package(
    path: Path,
    *,
    causal: bool = False,
    causal_factors: bool = False,
    omit_causal_factor: tuple[str, int] | None = None,
    no_allocation: bool = False,
    degenerate_uniform: bool = False,
    odd_unit: bool = False,
    other_property: bool = False,
    elec_in_kwh: bool = False,
    stray_waste_input: bool = False,
    regional: bool = False,
    regional_only: bool = False,
    unmapped_category: bool = False,
    no_location: bool = False,
    unknown_location: bool = False,
    widget_reference: float = 1.0,
) -> Path:
    """Write the package as a zip at path and return it."""
    with ZipWriter(str(path)) as writer:
        for group, (reference, others) in GROUPS.items():
            units = [
                o.Unit(
                    id=_id("unit", reference),
                    name=reference,
                    conversion_factor=1.0,
                    is_ref_unit=True,
                )
            ]
            units += [o.Unit(id=_id("unit", s), name=s, conversion_factor=f) for s, f in others]
            writer.write(o.UnitGroup(id=_id("group", group), name=f"Units of {group}", units=units))
        for prop, group in PROPERTIES.items():
            writer.write(
                o.FlowProperty(
                    id=_id("property", prop),
                    name=prop,
                    flow_property_type=o.FlowPropertyType.PHYSICAL_QUANTITY,
                    unit_group=_ref(o.RefType.UnitGroup, _id("group", group), f"Units of {group}"),
                )
            )
        writer.write(o.Location(id=_id("location", "GLO"), name="Global", code="GLO"))
        if regional or regional_only:
            writer.write(o.Location(id=_id("location", "CL"), name=LOCATIONS["CL"], code="CL"))
        for key, (name, prop, flow_type, category) in FLOWS.items():
            writer.write(
                o.Flow(
                    id=FLOW_IDS[key],
                    name=name,
                    flow_type=flow_type,
                    category=category,
                    cas="124-38-9" if key == "co2" else None,
                    flow_properties=[
                        o.FlowPropertyFactor(
                            flow_property=_property_ref(prop),
                            conversion_factor=1.0,
                            is_ref_flow_property=True,
                        )
                    ],
                )
            )
        lognormal = o.Uncertainty(
            distribution_type=o.UncertaintyType.LOG_NORMAL_DISTRIBUTION, geom_mean=2.0, geom_sd=1.2
        )
        degenerate = o.Uncertainty(
            distribution_type=o.UncertaintyType.UNIFORM_DISTRIBUTION, minimum=0.0, maximum=0.0
        )
        writer.write(
            _process(
                "elec",
                [
                    _exchange(
                        1,
                        "electricity",
                        1.0,
                        is_input=False,
                        reference=True,
                        unit="kWh" if elec_in_kwh else None,
                    ),
                    _exchange(2, "co2", 1.0, is_input=False),
                ],
            )
        )
        writer.write(
            _process(
                "steel",
                [
                    _exchange(1, "steel", 1.0, is_input=False, reference=True),
                    _exchange(
                        2,
                        "electricity",
                        2.0,
                        is_input=True,
                        unit="kWh",
                        provider=PROCESSES["elec"],
                        uncertainty=lognormal,
                    ),
                    _exchange(
                        3,
                        "co2",
                        500.0,
                        is_input=False,
                        unit="furlong" if odd_unit else "g",
                        uncertainty=degenerate if degenerate_uniform else None,
                    ),
                    _exchange(
                        4,
                        "ch4",
                        10.0,
                        is_input=False,
                        unit="g",
                        prop="Volume" if other_property else None,
                    ),
                ],
                location=None if no_location else "GLO",
                location_id=MISSING_LOCATION if unknown_location else None,
            )
        )
        allocation = (
            o.AllocationType.CAUSAL_ALLOCATION if causal else o.AllocationType.PHYSICAL_ALLOCATION
        )
        if no_allocation:
            allocation = o.AllocationType.NO_ALLOCATION
        allocation_factors = [_factor("fuel", 0.75), _factor("gas", 0.25)]
        if causal_factors:
            allocation_factors = [
                _causal_factor(product, exchange, value)
                for product, exchange, value in (
                    ("fuel", 3, 0.9),
                    ("gas", 3, 0.1),
                    ("fuel", 4, 0.5),
                    ("gas", 4, 0.5),
                )
                if (product, exchange) != omit_causal_factor
            ]
        writer.write(
            _process(
                "refinery",
                [
                    _exchange(1, "fuel", 1.0, is_input=False, reference=True),
                    _exchange(2, "gas", 1.0, is_input=False),
                    _exchange(3, "electricity", 4.0, is_input=True, provider=PROCESSES["elec"]),
                    _exchange(4, "co2", 2.0, is_input=False),
                ],
                default_allocation_method=allocation,
                allocation_factors=allocation_factors,
            )
        )
        widget = [
            _exchange(1, "widget", widget_reference, is_input=False, reference=True),
            _exchange(2, "steel", 0.5, is_input=True, provider=PROCESSES["steel"]),
            _exchange(3, "fuel", 1.0, is_input=True),
            _exchange(4, "part", 1.0, is_input=True, provider=MISSING_PROVIDER),
            _exchange(5, "scrap", 0.1, is_input=False, provider=PROCESSES["treatment"]),
            _exchange(6, "co2", 0.1, is_input=False),
            _exchange(7, "water", 0.02, is_input=True),
        ]
        if stray_waste_input:
            widget.append(
                _exchange(8, "scrap", 0.2, is_input=True, provider=PROCESSES["treatment"])
            )
        writer.write(_process("widget", widget, category="Manufacturing/assembly"))
        writer.write(
            _process(
                "treatment",
                [
                    _exchange(1, "scrap", 1.0, is_input=True, reference=True),
                    _exchange(2, "co2", 0.3, is_input=False),
                ],
            )
        )
        climate_factors = [_impact("co2", "Mass", "kg", 1.0), _impact("ch4", "Mass", "g", 0.028)]
        if regional:
            climate_factors.append(_impact("co2", "Mass", "kg", 5.0, "CL"))
        if regional_only:
            climate_factors.append(_impact("water", "Volume", "m3", 1.0, "CL"))
        climate = o.ImpactCategory(
            id=_id("category", "climate"),
            name="climate change",
            ref_unit="kg CO2-Eq",
            impact_factors=climate_factors,
        )
        water = o.ImpactCategory(
            id=_id("category", "water"),
            name="water use",
            ref_unit="m3",
            impact_factors=[_impact("water", "Volume", "m3", 1.0)],
        )
        writer.write(climate)
        writer.write(water)
        categories = [
            _ref(o.RefType.ImpactCategory, climate.id, climate.name),
            _ref(o.RefType.ImpactCategory, water.id, water.name),
        ]
        if unmapped_category:
            land = o.ImpactCategory(
                id=_id("category", "land"),
                name="land use",
                ref_unit="m2*a",
                impact_factors=[_impact("water", "Volume", "m3", 1.0)],
            )
            writer.write(land)
            categories.append(_ref(o.RefType.ImpactCategory, land.id, land.name))
        writer.write(
            o.ImpactMethod(
                id=_id("method", METHOD),
                name=METHOD,
                impact_categories=categories,
            )
        )
    return path
