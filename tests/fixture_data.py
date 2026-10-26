"""A synthetic background as constants: twelve processes, four elementary flows and two methods,
and a looped background of three."""

from __future__ import annotations

import uuid

from ecosemantic.model.refs import Database

NS = uuid.UUID("2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f")
FIXTURE_DB = "fixture"
FIXTURE_BIO = "fixture-biosphere"
GWP = ("fixture", "gwp", "climate change", "GWP100")
WATER = ("fixture", "water", "water use", "m3")
FIXTURE_FINGERPRINT = "ab4a4851ae4bc8a41d356d0da3b12a8727e59dcd7f46776f7016caa670b616d9"
FIXTURE_DATABASE = Database(
    name=FIXTURE_DB,
    elementary_flows=FIXTURE_BIO,
    scheme="olca",
    version="1",
    system_model="unit process",
    fingerprint=FIXTURE_FINGERPRINT,
)

FLOWS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "co2": ("Carbon dioxide, fossil", ("air",), "kilogram"),
    "ch4": ("Methane, fossil", ("air",), "kilogram"),
    "water_in": ("Water, river", ("natural resource", "in water"), "cubic meter"),
    "pm": ("Particulate matter", ("air", "urban air close to ground"), "kilogram"),
}
FLOW_IDS: dict[str, str] = {key: str(uuid.uuid5(NS, "flow:" + key)) for key in FLOWS}

PROCESSES: dict[str, tuple[str, str, str, dict[str, float], dict[str, float]]] = {
    "elec": ("electricity production", "electricity", "kilowatt hour", {}, {"co2": 1.0}),
    "steel": ("steel production", "steel", "kilogram", {"elec": 2.0}, {"co2": 0.5, "ch4": 0.01}),
    "lorry": ("transport, lorry", "transport", "ton kilometer", {}, {"co2": 0.1, "pm": 0.001}),
    "water": (
        "tap water production",
        "tap water",
        "kilogram",
        {"elec": 0.001},
        {"water_in": 0.001},
    ),
    "plastic": ("polyethylene production", "polyethylene", "kilogram", {"elec": 3.0}, {"co2": 2.0}),
    "glass": ("glass production", "glass", "kilogram", {"elec": 1.5}, {"co2": 0.8}),
    "paper": (
        "paper production",
        "paper",
        "kilogram",
        {"elec": 0.5, "water": 10.0},
        {"co2": 0.3},
    ),
    "cotton": (
        "cotton fibre production",
        "cotton fibre",
        "kilogram",
        {"elec": 0.2, "water": 50.0},
        {"co2": 0.4, "ch4": 0.02},
    ),
    "aluminium": ("aluminium production", "aluminium", "kilogram", {"elec": 15.0}, {"co2": 1.5}),
    "copper": ("copper production", "copper", "kilogram", {"elec": 5.0}, {"co2": 1.0}),
    "diesel": ("diesel production", "diesel", "kilogram", {}, {"co2": 3.2}),
    "wood": ("wood production", "wood", "kilogram", {"elec": 0.1}, {"co2": 0.05}),
}
CODES: dict[str, str] = {
    key: f"{uuid.uuid5(NS, 'process:' + key)}_{uuid.uuid5(NS, 'product:' + key)}"
    for key in PROCESSES
}
METHODS: tuple[tuple[tuple[str, ...], str, dict[str, float]], ...] = (
    (GWP, "kg CO2-Eq", {"co2": 1.0, "ch4": 28.0}),
    (WATER, "m3", {"water_in": 1.0}),
)
WIDE_NORMALS: dict[tuple[str, str], float] = {("elec", "co2"): 5.0, ("steel", "elec"): 3.0}

LOOP_DB = "looped"
LOOP_BIO = "looped-biosphere"
LOOP_PREFIX = "looped"
LOOP_GWP = ("looped", "gwp", "climate change", "GWP100")
LOOP_PROCESSES: dict[str, tuple[str, str, dict[str, tuple[float, float]], float]] = {
    "pellet": ("pellet production", "kilogram", {"heat": (3.45, 1.3)}, 0.01),
    "heat": ("heat production", "megajoule", {"pellet": (0.2, 2.0)}, 0.05),
    "elec": ("electricity production", "kilowatt hour", {}, 0.5),
}
LOOP_CODES: dict[str, str] = {
    key: f"{uuid.uuid5(NS, 'loop-process:' + key)}_{uuid.uuid5(NS, 'loop-product:' + key)}"
    for key in LOOP_PROCESSES
}
