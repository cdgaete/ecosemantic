"""The two systems a reply's size is measured on: nine staged cards from a mine to a refinery, and
a hundred cards in ten stages, both solvable on the synthetic background, with the lengths an
answer is counted at and the function that counts it."""

from __future__ import annotations

import json

from fastmcp.client.client import CallToolResult
from mcp.types import TextContent

from ecosemantic.model.entities import Case, Exchange, Parameter, Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef
from tests.conftest import uid
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DATABASE, FIXTURE_DB, FLOW_IDS

REPLY_BYTES = 8192
CODE_CHARS = 43
VARIANT_CHARS = 60
NAME_CHARS = 80
LONG_VIEW_URL = f"http://127.0.0.1:34157/?token={'a' * 43}"
STAGE_SIZE = 10
STAGE_COUNT = 10


def rendered_bytes(result: CallToolResult) -> int:
    """How many bytes pi renders one answer as: its text channel, a newline, and the same content
    indented by two, in UTF-8."""
    text = "".join(block.text for block in result.content if isinstance(block, TextContent))
    return len(
        f"{text}\n{json.dumps(result.structured_content, indent=2, ensure_ascii=False)}".encode()
    )


def rendered_size(structured: dict[str, object]) -> int:
    """How many bytes pi renders one answer as, counted from the structured content alone: the
    text channel, the SDK's compact JSON copy of it, a newline, and the same content indented by
    two, in UTF-8."""
    body = json.dumps(structured, separators=(",", ":"), ensure_ascii=False)
    copy = json.dumps(structured, indent=2, ensure_ascii=False)
    return len(f"{body}\n{copy}".encode())


def _exchange(
    process: str,
    n: int,
    type_: str,
    name: str,
    amount: float,
    unit: str,
    input_: BackgroundRef | ElementaryFlowRef | ForegroundRef | None = None,
    formula: str | None = None,
) -> Exchange:
    return Exchange(
        id=uid("layout-ex", process, str(n)),
        type=type_,
        name=name,
        amount=amount,
        unit=unit,
        input=input_,
        formula=formula,
    )


def _process(code: str, name: str, unit: str, stage: str, exchanges: list[Exchange]) -> Process:
    return Process(
        id=uid("layout-act", code),
        code=code,
        name=name,
        unit=unit,
        location="GLO",
        reference_product=name,
        metadata={"life_cycle_stage": stage},
        exchanges=exchanges,
    )


def _background(key: str) -> BackgroundRef:
    return BackgroundRef(database=FIXTURE_DB, id=CODES[key])


def _flow(key: str) -> ElementaryFlowRef:
    return ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS[key])


def staged_nine() -> ProductSystem:
    """Nine staged processes: a mine, a concentrator taking more input rows than a card draws
    before its fold, a lorry, a smelter and a refinery, electricity from a grid the sun feeds, and
    desalinated water; the refinery takes electricity on two exchanges, and the case `heavy`
    doubles the ore the concentrator takes."""
    mine_code, concentrator, lorry, smelter, refinery = (
        "mine",
        "concentrator",
        "transport",
        "smelter",
        "refinery",
    )
    grid, sun, desal, water = "grid", "sen", "desal", "water"
    mined = ForegroundRef(code=mine_code)
    concentrated = ForegroundRef(code=concentrator)
    carried = ForegroundRef(code=lorry)
    smelted = ForegroundRef(code=smelter)
    electricity = ForegroundRef(code=grid)
    watered = ForegroundRef(code=water)
    salty = ForegroundRef(code=desal)
    processes = [
        _process(
            mine_code,
            "copper ore",
            "kilogram",
            "extraction",
            [
                _exchange(mine_code, 0, "production", "copper ore", 1.0, "kilogram"),
                _exchange(
                    mine_code, 1, "product", "electricity", 0.5, "kilowatt hour", electricity
                ),
                _exchange(mine_code, 2, "product", "water", 2.0, "kilogram", watered),
                _exchange(
                    mine_code,
                    3,
                    "elementary",
                    "Carbon dioxide, fossil",
                    0.02,
                    "kilogram",
                    _flow("co2"),
                ),
            ],
        ),
        _process(
            concentrator,
            "copper concentrate",
            "kilogram",
            "processing",
            [
                _exchange(concentrator, 0, "production", "copper concentrate", 1.0, "kilogram"),
                _exchange(
                    concentrator, 1, "product", "copper ore", 2.5, "kilogram", mined, "ore_mass"
                ),
                _exchange(
                    concentrator, 2, "product", "diesel", 0.3, "kilogram", _background("diesel")
                ),
                _exchange(concentrator, 3, "product", "wood", 0.1, "kilogram", _background("wood")),
                _exchange(
                    concentrator,
                    4,
                    "product",
                    "polyethylene",
                    0.05,
                    "kilogram",
                    _background("plastic"),
                ),
                _exchange(
                    concentrator, 5, "product", "glass", 0.02, "kilogram", _background("glass")
                ),
                _exchange(
                    concentrator,
                    6,
                    "product",
                    "aluminium",
                    0.03,
                    "kilogram",
                    _background("aluminium"),
                ),
                _exchange(concentrator, 7, "product", "water", 1.5, "kilogram", watered),
                _exchange(
                    concentrator, 8, "product", "electricity", 0.8, "kilowatt hour", electricity
                ),
                _exchange(
                    concentrator,
                    9,
                    "elementary",
                    "Carbon dioxide, fossil",
                    0.05,
                    "kilogram",
                    _flow("co2"),
                ),
            ],
        ),
        _process(
            lorry,
            "transport, freight",
            "ton kilometer",
            "transport",
            [
                _exchange(lorry, 0, "production", "transport, freight", 1.0, "ton kilometer"),
                _exchange(lorry, 1, "product", "copper concentrate", 2.5, "kilogram", concentrated),
                _exchange(lorry, 2, "product", "diesel", 0.05, "kilogram", _background("diesel")),
                _exchange(lorry, 3, "product", "electricity", 0.2, "kilowatt hour", electricity),
                _exchange(
                    lorry, 4, "elementary", "Carbon dioxide, fossil", 0.01, "kilogram", _flow("co2")
                ),
            ],
        ),
        _process(
            smelter,
            "copper anode",
            "kilogram",
            "smelting",
            [
                _exchange(smelter, 0, "production", "copper anode", 1.0, "kilogram"),
                _exchange(smelter, 1, "product", "copper concentrate", 2.5, "kilogram", carried),
                _exchange(smelter, 2, "product", "electricity", 1.2, "kilowatt hour", electricity),
                _exchange(
                    smelter,
                    3,
                    "elementary",
                    "Carbon dioxide, fossil",
                    0.3,
                    "kilogram",
                    _flow("co2"),
                ),
            ],
        ),
        _process(
            refinery,
            "refined copper",
            "kilogram",
            "refining",
            [
                _exchange(refinery, 0, "production", "refined copper", 1.0, "kilogram"),
                _exchange(refinery, 1, "product", "copper anode", 1.05, "kilogram", smelted),
                _exchange(
                    refinery,
                    2,
                    "product",
                    "electricity, low voltage",
                    0.6,
                    "kilowatt hour",
                    electricity,
                ),
                _exchange(
                    refinery,
                    3,
                    "product",
                    "electricity, high voltage",
                    0.4,
                    "kilowatt hour",
                    electricity,
                ),
                _exchange(
                    refinery,
                    4,
                    "elementary",
                    "Carbon dioxide, fossil",
                    0.02,
                    "kilogram",
                    _flow("co2"),
                ),
            ],
        ),
        _process(
            grid,
            "electricity",
            "kilowatt hour",
            "energy",
            [
                _exchange(grid, 0, "production", "electricity", 1.0, "kilowatt hour"),
                _exchange(
                    grid,
                    1,
                    "product",
                    "electricity from the sun",
                    0.3,
                    "kilowatt hour",
                    ForegroundRef(code=sun),
                ),
                _exchange(
                    grid, 2, "elementary", "Carbon dioxide, fossil", 0.4, "kilogram", _flow("co2")
                ),
            ],
        ),
        _process(
            sun,
            "electricity from the sun",
            "kilowatt hour",
            "energy",
            [
                _exchange(sun, 0, "production", "electricity from the sun", 1.0, "kilowatt hour"),
                _exchange(
                    sun, 1, "elementary", "Particulate matter", 0.0001, "kilogram", _flow("pm")
                ),
            ],
        ),
        _process(
            desal,
            "desalinated water",
            "kilogram",
            "extraction",
            [
                _exchange(desal, 0, "production", "desalinated water", 1.0, "kilogram"),
                _exchange(desal, 1, "product", "electricity", 4.0, "kilowatt hour", electricity),
                _exchange(
                    desal, 2, "elementary", "Water, river", 0.001, "cubic meter", _flow("water_in")
                ),
            ],
        ),
        _process(
            water,
            "tap water",
            "kilogram",
            "extraction",
            [
                _exchange(water, 0, "production", "tap water", 1.0, "kilogram"),
                _exchange(water, 1, "product", "desalinated water", 1.0, "kilogram", salty),
                _exchange(water, 2, "product", "electricity", 0.3, "kilowatt hour", electricity),
                _exchange(
                    water, 3, "elementary", "Water, river", 0.01, "cubic meter", _flow("water_in")
                ),
            ],
        ),
    ]
    return ProductSystem(
        id=uid("layout-product_system", "staged-nine"),
        name="refined copper",
        database=FIXTURE_DATABASE,
        processes=processes,
        parameters=[Parameter(name="ore_mass", value=2.5, unit="kilogram")],
        cases=[Case(name="heavy", values={"ore_mass": 5.0})],
        reference_process=refinery,
    )


def _padded(text: str, length: int) -> str:
    return text + "." * (length - len(text))


def _hundred_code(stage: int, index: int) -> str:
    stem = f"s{stage}{index:02d}-"
    tail = f"-{stage}{index:02d}"
    return stem + "x" * (CODE_CHARS - len(stem) - len(tail)) + tail


def _hundred_name(stage: int, index: int, n: int) -> str:
    return _padded(f"input {n} of process {stage}-{index}", NAME_CHARS)


def hundred() -> ProductSystem:
    """A hundred processes in ten stages of ten: each fed by two of the stage before and by
    electricity from the background, a parameter its first stage reads on a formula, and a
    reference taking twenty exchanges."""
    codes = {
        (stage, index): _hundred_code(stage, index)
        for stage in range(STAGE_COUNT)
        for index in range(STAGE_SIZE)
    }
    electricity = _background("elec")
    processes = []
    for stage in range(STAGE_COUNT):
        for index in range(STAGE_SIZE):
            code = codes[stage, index]
            exchanges = [
                _exchange(code, 0, "production", f"production of {stage}-{index}", 1.0, "kilogram"),
            ]
            for n, source in enumerate(
                ((stage - 1, 2 * index % STAGE_SIZE), (stage - 1, (2 * index + 1) % STAGE_SIZE))
                if stage > 0
                else ()
            ):
                exchanges.append(
                    _exchange(
                        code,
                        n + 1,
                        "product",
                        _hundred_name(stage, index, n),
                        2.0 - n * 0.5,
                        "kilogram",
                        ForegroundRef(code=codes[source]),
                    )
                )
            exchanges.append(
                _exchange(
                    code,
                    STAGE_SIZE,
                    "product",
                    _hundred_name(stage, index, 2),
                    2.0 if (stage, index) == (0, 0) else 0.5,
                    "kilowatt hour",
                    electricity,
                    "ore * 2" if (stage, index) == (0, 0) else None,
                )
            )
            exchanges.append(
                _exchange(
                    code,
                    STAGE_SIZE + 1,
                    "elementary",
                    "Carbon dioxide, fossil",
                    0.01 * (index + 1),
                    "kilogram",
                    _flow("co2"),
                )
            )
            processes.append(
                _process(code, f"process {stage}-{index}", "kilogram", f"stage {stage}", exchanges)
            )
    reference = codes[STAGE_COUNT - 1, 0]
    top = next(process for process in processes if process.code == reference)
    for n, index in enumerate(range(1, STAGE_SIZE)):
        top.exchanges.append(
            _exchange(
                reference,
                20 + n,
                "product",
                _hundred_name(9, 0, 4 + n),
                2.0,
                "kilogram",
                ForegroundRef(code=codes[STAGE_COUNT - 1, index]),
            )
        )
    for n, (key, amount) in enumerate(
        [
            ("steel", 0.1),
            ("lorry", 0.2),
            ("plastic", 0.05),
            ("glass", 0.02),
            ("aluminium", 0.03),
            ("water", 0.5),
        ]
    ):
        top.exchanges.append(
            _exchange(
                reference,
                40 + n,
                "product",
                _hundred_name(9, 0, 13 + n),
                amount,
                "kilogram",
                _background(key),
            )
        )
    for n, (key, amount) in enumerate((("ch4", 0.002), ("water_in", 0.003), ("pm", 0.0004))):
        top.exchanges.append(
            _exchange(
                reference,
                50 + n,
                "elementary",
                _hundred_name(9, 0, 19),
                amount,
                "kilogram",
                _flow(key),
            )
        )
    return ProductSystem(
        id=uid("layout-product_system", "hundred"),
        name="hundred",
        database=FIXTURE_DATABASE,
        processes=processes,
        parameters=[Parameter(name="ore", value=1.0, unit="kilogram")],
        cases=[Case(name=_padded("ore doubled", VARIANT_CHARS), values={"ore": 3.0})],
        reference_process=reference,
    )
