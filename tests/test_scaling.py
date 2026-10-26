from __future__ import annotations

import uuid

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.geometry import linked_code
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Database, Exchange, Process, ProductSystem
from ecosemantic.model.refs import ForegroundRef, LinkedProcessRef, SystemRef
from ecosemantic.ports.types import Activity
from ecosemantic.scaling import scale
from tests.conftest import frame_system, widget_linking

DATABASE = Database(
    name="d", elementary_flows="e", scheme="olca", version="1", system_model="unit process"
)


def _ex(type_: str, amount: float, input_: ForegroundRef | None = None) -> Exchange:
    return Exchange(id=uuid.uuid4(), type=type_, name=type_, amount=amount, unit="kg", input=input_)


def _process(code: str, produces: float, *inputs: Exchange) -> Process:
    return Process(
        id=uuid.uuid4(),
        code=code,
        name=code,
        unit="kg",
        location="GLO",
        reference_product=code,
        exchanges=[_ex("production", produces), *inputs],
    )


def _chain() -> ProductSystem:
    refinery = _process("refinery", 1.0, _ex("product", 1.005, ForegroundRef(code="smelter")))
    smelter = _process("smelter", 1.0, _ex("product", 3.7, ForegroundRef(code="mine")))
    mine = _process("mine", 1.0)
    return ProductSystem(
        id=uuid.uuid4(),
        name="chain",
        database=DATABASE,
        processes=[refinery, smelter, mine],
        reference_process="refinery",
    )


def test_a_processs_exchanges_are_its_amounts_times_its_activity() -> None:
    system = _chain()
    levels = {"refinery": 1.0, "smelter": 1.005, "mine": 1.005 * 3.7}
    found = scale(
        system, {}, [Activity(ref=ForegroundRef(code=c), level=v) for c, v in levels.items()]
    )
    smelter = system.process("smelter")
    assert found["smelter"].activity == 1.005
    production = next(e for e in smelter.exchanges if e.type == "production")
    assert found["smelter"].amounts[production.id] == pytest.approx(1.005)
    inputs = [e for e in smelter.exchanges if e.type == "product"]
    assert found["smelter"].amounts[inputs[0].id] == pytest.approx(1.005 * 3.7)


def test_a_production_of_two_at_half_a_run_is_one_unit() -> None:
    process = _process("p", 2.0)
    system = ProductSystem(
        id=uuid.uuid4(), name="s", database=DATABASE, processes=[process], reference_process="p"
    )
    found = scale(system, {}, [Activity(ref=ForegroundRef(code="p"), level=0.5)])
    assert list(found["p"].amounts.values()) == [1.0]


def test_a_linked_systems_card_is_its_reference_processs_production_at_its_level() -> None:
    frame = frame_system()
    frame = frame.model_copy(update={"hash": content_hash(frame)})
    widget = widget_linking(frame)
    link = next(e.input for e in widget.processes[0].exchanges if isinstance(e.input, SystemRef))
    production = next(e for e in frame.processes[0].exchanges if e.type == "production")
    found = scale(
        widget,
        {frame.id: frame},
        [
            Activity(ref=ForegroundRef(code="widget"), level=1.0),
            Activity(
                ref=LinkedProcessRef(
                    product_system_id=frame.id, at_hash=content_hash(frame), code="frame"
                ),
                level=0.25,
            ),
        ],
    )
    card = found[linked_code(link)]
    assert card.activity == 0.25
    assert card.amounts == {production.id: 0.25 * production.amount}


def test_a_linked_system_without_a_reference_process_is_refused() -> None:
    frame = frame_system().model_copy(update={"reference_process": None})
    widget = widget_linking(frame_system())
    link = next(e.input for e in widget.processes[0].exchanges if isinstance(e.input, SystemRef))
    with pytest.raises(Invalid, match="no reference process"):
        scale(
            widget,
            {link.product_system_id: frame},
            [Activity(ref=ForegroundRef(code="widget"), level=1.0)],
        )


def test_a_process_without_an_activity_level_is_refused_by_name() -> None:
    with pytest.raises(Invalid, match="refinery"):
        scale(_chain(), {}, [])


def test_a_linked_system_without_a_supplied_reference_process_is_refused_by_name() -> None:
    frame = frame_system()
    widget = widget_linking(frame)
    with pytest.raises(Invalid, match="frame"):
        scale(
            widget,
            {frame.id: frame},
            [Activity(ref=ForegroundRef(code="widget"), level=1.0)],
        )
