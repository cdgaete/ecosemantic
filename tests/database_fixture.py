"""Two product systems over the synthetic openLCA base: a casing with two cases, and a device
that links the casing's heavy case."""

from __future__ import annotations

import math
import uuid

from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import (
    Case,
    Exchange,
    Parameter,
    Process,
    ProductSystem,
    Uncertainty,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
)
from ecosemantic.ports.resolver import BackgroundInfo, FlowInfo
from tests.openlca_fixture import FLOW_IDS, NAME, PROCESSES

NS = uuid.UUID("61f0c1d2-3e4f-4a5b-9c6d-7e8f9a0b1c2d")
BASE = NAME
BIO = f"{NAME}-biosphere"
STEEL = BackgroundRef(database=BASE, id=f"{PROCESSES['steel']}_{FLOW_IDS['steel']}")
ELEC = BackgroundRef(database=BASE, id=f"{PROCESSES['elec']}_{FLOW_IDS['electricity']}")
CO2 = ElementaryFlowRef(database=BIO, id=FLOW_IDS["co2"])
BASE_FINGERPRINT = "106df31f2c5f21863be3b72bd496eb2d18c2170dbcce66b8014e56e7c9ca73e6"
DATABASE = Database(
    name=BASE,
    elementary_flows=BIO,
    scheme="olca",
    version="1",
    system_model="unit process",
    fingerprint=BASE_FINGERPRINT,
)


def _id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NS, "|".join(parts))


def _ex(
    code: str,
    n: int,
    type_: str,
    name: str,
    amount: float,
    unit: str,
    input_=None,
    formula=None,
    uncertainty=None,
) -> Exchange:
    return Exchange(
        id=_id("ex", code, str(n)),
        type=type_,
        name=name,
        amount=amount,
        unit=unit,
        input=input_,
        formula=formula,
        uncertainty=uncertainty,
    )


def casing_system() -> ProductSystem:
    """An assembly taking a casing; the coating is zero at the base and in the light case."""
    assembly = Process(
        id=_id("act", "assembly"),
        code="assembly",
        name="assembly",
        unit="unit",
        location="GLO",
        reference_product="assembled casing",
        exchanges=[
            _ex("assembly", 0, "production", "assembled casing", 1.0, "unit"),
            _ex(
                "assembly",
                1,
                "product",
                "casing",
                0.5,
                "kilogram",
                ForegroundRef(code="casing"),
                formula="casing_mass",
            ),
            _ex("assembly", 2, "product", "electricity", 2.0, "megajoule", ELEC),
            _ex(
                "assembly",
                3,
                "product",
                "coating steel",
                0.0,
                "kilogram",
                STEEL,
                formula="coating_mass",
            ),
        ],
    )
    casing = Process(
        id=_id("act", "casing"),
        code="casing",
        name="casing",
        unit="kilogram",
        location="GLO",
        reference_product="casing",
        exchanges=[
            _ex("casing", 0, "production", "casing", 1.0, "kilogram"),
            _ex(
                "casing",
                1,
                "product",
                "steel",
                1.1,
                "kilogram",
                STEEL,
                uncertainty=Uncertainty(
                    type="lognormal", params={"loc": math.log(1.1), "scale": 0.1}
                ),
            ),
            _ex("casing", 2, "elementary", "Carbon dioxide, fossil", 0.05, "kilogram", CO2),
        ],
    )
    return ProductSystem(
        id=_id("system", "casing"),
        name="casing",
        database=DATABASE,
        processes=[assembly, casing],
        reference_process="assembly",
        parameters=[
            Parameter(name="casing_mass", value=0.5, unit="kilogram"),
            Parameter(name="coating_mass", value=0.0, unit="kilogram"),
        ],
        cases=[
            Case(name="light", values={"casing_mass": 0.3}),
            Case(name="heavy", values={"casing_mass": 0.8, "coating_mass": 0.1}),
        ],
    )


def device_system(casing: ProductSystem) -> ProductSystem:
    """A device taking two assembled casings of the casing system's heavy case; no cases."""
    device = Process(
        id=_id("act", "device"),
        code="device",
        name="device",
        unit="unit",
        location="GLO",
        reference_product="device",
        exchanges=[
            _ex("device", 0, "production", "device", 1.0, "unit"),
            _ex(
                "device",
                1,
                "product",
                "assembled casing",
                2.0,
                "unit",
                SystemRef(product_system_id=casing.id, at_hash=content_hash(casing), case="heavy"),
            ),
            _ex("device", 2, "elementary", "Carbon dioxide, fossil", 0.2, "kilogram", CO2),
        ],
    )
    return ProductSystem(
        id=_id("system", "device"),
        name="device",
        database=DATABASE,
        processes=[device],
        reference_process="device",
    )


def backgrounds() -> dict[str, BackgroundInfo]:
    """What the resolver answers for the two base processes the systems name."""
    return {
        STEEL.id: BackgroundInfo(
            name="steel production",
            reference_product="steel, low-alloyed",
            location="GLO",
            unit="kilogram",
        ),
        ELEC.id: BackgroundInfo(
            name="elec production",
            reference_product="electricity, medium voltage",
            location="GLO",
            unit="megajoule",
        ),
    }


def flows() -> dict[str, FlowInfo]:
    """What the resolver answers for the one elementary flow the systems name."""
    return {
        CO2.id: FlowInfo(
            name="Carbon dioxide, fossil",
            compartment="air",
            sub_compartment=None,
            unit="kilogram",
            flow_type="emission",
        ),
    }
