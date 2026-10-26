from __future__ import annotations

import math
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import FastMCP

from ecosemantic.backends.native.store import NativeStore
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import (
    Case,
    Exchange,
    ExchangeOverride,
    Parameter,
    ParameterOverride,
    Process,
    ProductSystem,
    Scenario,
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
from ecosemantic.ports.types import System
from tests.dict_resolver import DictResolver
from tests.engine_fixture import install_fixtures
from tests.fixture_data import CODES as FIXTURE_CODES
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DATABASE, FIXTURE_DB
from tests.fixture_data import FLOW_IDS as FIXTURE_FLOWS

NS = uuid.UUID("6f1b5a5e-0c3e-4b52-9a1e-2f0d6c1a7d10")
EI = "ecoinvent-3.11-cutoff"
BIO = "ecoinvent-3.11-biosphere"
DATABASE = Database(
    name=EI, elementary_flows=BIO, scheme="ecoinvent", version="3.11", system_model="cutoff"
)


def native(name: str) -> str:
    """A synthetic native id: an activity's uuid and its product's, joined by an underscore."""
    return f"{uuid.uuid5(NS, 'activity|' + name)}_{uuid.uuid5(NS, 'product|' + name)}"


COTTON = BackgroundRef(database=EI, id=native("cotton fibre"))
ORGANIC = BackgroundRef(database=EI, id=native("organic cotton fibre"))
POLY = BackgroundRef(database=EI, id=native("polyester fibre"))
ELEC_CH = BackgroundRef(database=EI, id=native("medium-voltage electricity"))
WATER_CH = BackgroundRef(database=EI, id=native("tap water"))
LORRY = BackgroundRef(database=EI, id=native("lorry freight"))
CO2 = ElementaryFlowRef(database=BIO, id=str(uuid.uuid5(NS, "flow|carbon dioxide, fossil")))
CH4 = ElementaryFlowRef(database=BIO, id=str(uuid.uuid5(NS, "flow|methane, fossil")))
RIVER = ElementaryFlowRef(database=BIO, id=str(uuid.uuid5(NS, "flow|water, river")))


def uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NS, "|".join(parts))


def ex(
    code: str,
    n: int,
    type_: str,
    name: str,
    amount: float,
    unit: str,
    input_: BackgroundRef | ElementaryFlowRef | ForegroundRef | None = None,
    formula: str | None = None,
    comment: str | None = None,
    uncertainty: Uncertainty | None = None,
) -> Exchange:
    return Exchange(
        id=uid("ex", code, str(n)),
        type=type_,
        name=name,
        amount=amount,
        unit=unit,
        input=input_,
        formula=formula,
        comment=comment,
        uncertainty=uncertainty,
    )


def fixture_product_system() -> ProductSystem:
    """A cotton t-shirt: three foreground stages on ecoinvent 3.11, and organic yarn
    the fabric draws on in the share a parameter sets."""
    tshirt = Process(
        id=uid("act", "tshirt"),
        code="tshirt",
        name="cotton t-shirt, assembled",
        unit="unit",
        location="CH",
        reference_product="cotton t-shirt",
        comment="Functional unit: one t-shirt.",
        metadata={"life_cycle_stage": "manufacturing", "hierarchy_level": 0},
        exchanges=[
            ex("tshirt", 0, "production", "cotton t-shirt", 1.0, "unit"),
            ex(
                "tshirt",
                1,
                "product",
                "cotton fabric",
                0.2,
                "kilogram",
                ForegroundRef(code="fabric"),
                formula="fabric_mass",
            ),
            ex(
                "tshirt",
                2,
                "product",
                "sewing electricity",
                0.3,
                "kilowatt hour",
                ELEC_CH,
                formula="elec_per_kg * fabric_mass",
                uncertainty=Uncertainty(
                    type="lognormal", params={"loc": math.log(0.3), "scale": 0.2}
                ),
            ),
            ex(
                "tshirt",
                3,
                "product",
                "transport to warehouse",
                0.0005,
                "ton kilometer",
                LORRY,
                comment="500 km by lorry",
                uncertainty=Uncertainty(
                    type="lognormal", params={"loc": math.log(0.0005), "scale": 0.3}
                ),
            ),
            ex("tshirt", 4, "elementary", "Carbon dioxide, fossil", 0.01, "kilogram", CO2),
        ],
    )
    fabric = Process(
        id=uid("act", "fabric"),
        code="fabric",
        name="cotton fabric",
        unit="kilogram",
        location="CH",
        reference_product="cotton fabric",
        metadata={"life_cycle_stage": "manufacturing", "hierarchy_level": 1},
        exchanges=[
            ex("fabric", 0, "production", "cotton fabric", 1.0, "kilogram"),
            ex(
                "fabric",
                1,
                "product",
                "cotton yarn",
                1.1,
                "kilogram",
                ForegroundRef(code="yarn"),
                uncertainty=Uncertainty(
                    type="triangular", params={"minimum": 1.05, "loc": 1.1, "maximum": 1.2}
                ),
            ),
            ex("fabric", 2, "product", "weaving electricity", 2.0, "kilowatt hour", ELEC_CH),
            ex("fabric", 3, "product", "tap water", 50.0, "kilogram", WATER_CH),
            ex("fabric", 4, "elementary", "Water, river", 0.02, "cubic meter", RIVER),
            ex(
                "fabric",
                5,
                "product",
                "organic cotton yarn",
                0.0,
                "kilogram",
                ForegroundRef(code="organic_yarn"),
                formula="1.1 * organic_share",
            ),
        ],
    )
    yarn = Process(
        id=uid("act", "yarn"),
        code="yarn",
        name="cotton yarn",
        unit="kilogram",
        location="GLO",
        reference_product="cotton yarn",
        metadata={"life_cycle_stage": "raw_material_extraction", "hierarchy_level": 2},
        exchanges=[
            ex("yarn", 0, "production", "cotton yarn", 1.0, "kilogram"),
            ex("yarn", 1, "product", "cotton fibre", 1.05, "kilogram", COTTON),
            ex("yarn", 2, "product", "polyester fibre", 0.05, "kilogram", POLY),
            ex("yarn", 3, "elementary", "Methane, fossil", 0.001, "kilogram", CH4),
        ],
    )
    organic_yarn = Process(
        id=uid("act", "organic_yarn"),
        code="organic_yarn",
        name="organic cotton yarn",
        unit="kilogram",
        location="GLO",
        reference_product="organic cotton yarn",
        exchanges=[
            ex("organic_yarn", 0, "production", "organic cotton yarn", 1.0, "kilogram"),
            ex(
                "organic_yarn",
                1,
                "product",
                "organic cotton fibre",
                1.05,
                "kilogram",
                ORGANIC,
            ),
        ],
    )
    system = ProductSystem(
        id=uid("product_system", "cotton_tshirt"),
        name="cotton_tshirt",
        description="One cotton t-shirt, cradle to gate.",
        notes="Fixture.",
        database=DATABASE,
        processes=[tshirt, fabric, yarn, organic_yarn],
        reference_process="tshirt",
        parameters=[
            Parameter(
                name="fabric_mass", value=0.2, unit="kilogram", description="fabric per shirt"
            ),
            Parameter(name="waste_rate", value=0.1, description="cutting waste fraction"),
            Parameter(
                name="elec_per_kg", value=1.5, unit="kWh/kg", description="sewing electricity"
            ),
            Parameter(name="fibre_mass", formula="fabric_mass * (1 + waste_rate)", unit="kilogram"),
            Parameter(name="organic_share", value=0.0, description="organic yarn share"),
        ],
        cases=[
            Case(name="small", description="size S", values={"fabric_mass": 0.15}),
            Case(name="large", description="size L", values={"fabric_mass": 0.25}),
        ],
        scenarios=[
            Scenario(
                name="organic",
                description="organic cotton, half the sewing electricity, less waste",
                overrides=[
                    ExchangeOverride(exchange_id=tshirt.exchanges[2].id, multiplier=0.5),
                    ExchangeOverride(exchange_id=yarn.exchanges[1].id, input=ORGANIC),
                    ParameterOverride(name="waste_rate", value=0.05),
                ],
            )
        ],
    )
    system.scenarios[0].base_hash = base_pin(system)
    return system


@pytest.fixture
def product_system() -> ProductSystem:
    return fixture_product_system()


BACKGROUNDS = {
    COTTON.id: BackgroundInfo(
        name="cotton fibre supply",
        reference_product="cotton fibre",
        location="GLO",
        unit="kilogram",
    ),
    ORGANIC.id: BackgroundInfo(
        name="organic cotton fibre supply",
        reference_product="organic cotton fibre",
        location="GLO",
        unit="kilogram",
    ),
    POLY.id: BackgroundInfo(
        name="polyester fibre supply",
        reference_product="polyester fibre",
        location="GLO",
        unit="kilogram",
    ),
    ELEC_CH.id: BackgroundInfo(
        name="medium-voltage electricity supply",
        reference_product="medium-voltage electricity",
        location="CH",
        unit="kilowatt hour",
    ),
    WATER_CH.id: BackgroundInfo(
        name="tap water supply", reference_product="tap water", location="CH", unit="kilogram"
    ),
    LORRY.id: BackgroundInfo(
        name="lorry freight",
        reference_product="lorry freight",
        location="RER",
        unit="ton kilometer",
    ),
}
FLOWS = {
    CO2.id: FlowInfo(
        name="Carbon dioxide, fossil",
        compartment="air",
        sub_compartment=None,
        unit="kilogram",
        flow_type="emission",
    ),
    CH4.id: FlowInfo(
        name="Methane, fossil",
        compartment="air",
        sub_compartment=None,
        unit="kilogram",
        flow_type="emission",
    ),
    RIVER.id: FlowInfo(
        name="Water, river",
        compartment="natural resource",
        sub_compartment="in water",
        unit="cubic meter",
        flow_type="natural resource",
    ),
}


@pytest.fixture
def resolver() -> DictResolver:
    return DictResolver(BACKGROUNDS, FLOWS)


@pytest.fixture(autouse=True)
def _telemetry_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test counts a start or reaches a collector unless it switches telemetry on itself."""
    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY", "off")
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory of its own, so no test reads or writes the person's clients."""
    folder = tmp_path / "home"
    folder.mkdir()
    # Path.home reads HOME on POSIX and USERPROFILE on Windows
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("ECOSEMANTIC_DATA_DIR", raising=False)
    # the session's own Linux config home and display reach no client's file
    for name in ("XDG_CONFIG_HOME", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    return folder


@pytest.fixture
def command(tmp_path: Path) -> Path:
    """An installed command to point a client at, under a path whose text holds backslashes:
    Windows separates with them, and on POSIX the folder's own name holds them."""
    folder = tmp_path / ("tools" if sys.platform == "win32" else "C:\\tools\\ecosemantic")
    folder.mkdir()
    made = folder / "ecosemantic.exe"
    made.write_text("")
    return made


@pytest.fixture(scope="session")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("data")
    install_fixtures(directory, tmp_path_factory.mktemp("sources"))
    return directory


@pytest.fixture(scope="session")
def native_store(bundle_dir: Path) -> Iterator[NativeStore]:
    instance = NativeStore(bundle_dir)
    yield instance
    instance.close()


def fixture_system() -> System:
    """A widget and its frame on the synthetic background; widget scores 4.158, frame 6.672."""
    steel = BackgroundRef(database=FIXTURE_DB, id=FIXTURE_CODES["steel"])
    elec = BackgroundRef(database=FIXTURE_DB, id=FIXTURE_CODES["elec"])
    co2 = ElementaryFlowRef(database=FIXTURE_BIO, id=FIXTURE_FLOWS["co2"])
    database = FIXTURE_DATABASE

    def fex(
        code: str,
        n: int,
        type_: str,
        name: str,
        amount: float,
        unit: str,
        input_: BackgroundRef | ElementaryFlowRef | ForegroundRef | None = None,
        uncertainty: Uncertainty | None = None,
    ) -> Exchange:
        return Exchange(
            id=uid("fixture-ex", code, name, str(n)),
            type=type_,
            name=name,
            amount=amount,
            unit=unit,
            input=input_,
            uncertainty=uncertainty,
        )

    widget = Process(
        id=uid("fixture-act", "widget"),
        code="widget",
        name="widget assembly",
        unit="unit",
        location="GLO",
        reference_product="widget",
        exchanges=[
            fex("widget", 0, "production", "widget", 1.0, "unit"),
            fex(
                "widget",
                1,
                "product",
                "steel",
                0.5,
                "kilogram",
                steel,
                Uncertainty(type="lognormal", params={"loc": math.log(0.5), "scale": 0.1}),
            ),
            fex("widget", 2, "product", "electricity", 1.0, "kilowatt hour", elec),
            fex("widget", 3, "product", "frame", 0.25, "kilogram", ForegroundRef(code="frame")),
            fex("widget", 4, "elementary", "Carbon dioxide, fossil", 0.1, "kilogram", co2),
        ],
    )
    frame = Process(
        id=uid("fixture-act", "frame"),
        code="frame",
        name="frame production",
        unit="kilogram",
        location="GLO",
        reference_product="frame",
        exchanges=[
            fex("frame", 0, "production", "frame", 1.0, "kilogram"),
            fex("frame", 1, "product", "steel", 2.4, "kilogram", steel),
        ],
    )
    product_system = ProductSystem(
        id=uid("fixture-product_system", "widget"),
        name="widget",
        database=database,
        processes=[widget, frame],
        reference_process="widget",
    )
    return System(database=FIXTURE_DB, product_system=product_system)


@pytest.fixture(name="fixture_system")
def fixture_system_fixture() -> System:
    return fixture_system()


@pytest.fixture(scope="session")
def systems_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("systems")


@pytest.fixture(scope="session")
def context(bundle_dir: Path, systems_dir: Path) -> Iterator[ServerContext]:
    built = build_context(bundle_dir, systems_dir)
    yield built
    built.close()


@pytest.fixture(scope="session")
async def fixture_system_stored(context: ServerContext) -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    await context.storage.put_product_system(system, context.actor, "created")
    return system


def frame_system() -> ProductSystem:
    """The fixture's frame as a product system of its own; a kilogram scores 6.672."""
    whole = fixture_system().product_system
    assert whole is not None
    return ProductSystem(
        id=uid("fixture-product_system", "frame"),
        name="frame",
        database=whole.database,
        processes=[whole.process("frame").model_copy(deep=True)],
        reference_process="frame",
    )


def widget_linking(frame: ProductSystem) -> ProductSystem:
    """The fixture's widget taking a quarter kilogram of the frame system at its content hash;
    it scores the fixture's 4.158."""
    whole = fixture_system().product_system
    assert whole is not None
    widget = whole.process("widget").model_copy(deep=True)
    for exchange in widget.exchanges:
        if isinstance(exchange.input, ForegroundRef):
            exchange.input = SystemRef(product_system_id=frame.id, at_hash=content_hash(frame))
    return ProductSystem(
        id=uid("fixture-product_system", "widget-linking"),
        name="widget_linking",
        database=whole.database,
        processes=[widget],
        reference_process="widget",
    )


def split_system() -> System:
    """The widget linking the frame, as a calculation takes them: the frame read at its hash."""
    frame = frame_system()
    frame = frame.model_copy(update={"hash": content_hash(frame)})
    return System.of(widget_linking(frame), {frame.id: frame})


@pytest.fixture(scope="session")
async def linked_stored(context: ServerContext) -> tuple[ProductSystem, ProductSystem]:
    """The widget linking the frame, stored after the frame; the widget first."""
    frame = frame_system()
    await context.storage.put_product_system(frame, context.actor, "created")
    widget = widget_linking(frame)
    await context.storage.put_product_system(widget, context.actor, "created")
    return widget, frame


def label_system() -> ProductSystem:
    """A care label as a product system on the t-shirt's database, its one process its
    reference."""
    label = Process(
        id=uid("act", "label"),
        code="label",
        name="care label",
        unit="unit",
        location="GLO",
        reference_product="care label",
        exchanges=[ex("label", 0, "production", "care label", 1.0, "unit")],
    )
    return ProductSystem(
        id=uid("product_system", "label"),
        name="label",
        database=DATABASE,
        processes=[label],
        reference_process="label",
    )


def tshirt_labelled(product_system: ProductSystem, label: ProductSystem) -> ProductSystem:
    """The t-shirt taking one label at the label system's content hash."""
    out = product_system.model_copy(deep=True)
    out.process("tshirt").exchanges.append(
        Exchange(
            id=uid("ex", "tshirt", "label"),
            type="product",
            name="care label",
            amount=1.0,
            unit="unit",
            input=SystemRef(product_system_id=label.id, at_hash=content_hash(label)),
        )
    )
    return out


@pytest.fixture(scope="session")
def full_server(context: ServerContext) -> FastMCP:
    return build_server(context)
