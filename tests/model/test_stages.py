"""The life-cycle stage of a process, and the order a system's stages come in."""

from __future__ import annotations

import uuid

from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.stages import stage_of, stage_order
from tests.conftest import fixture_system


def _restaged(system: ProductSystem, stages: dict[str, str | None]) -> ProductSystem:
    processes = [
        process.model_copy(
            deep=True,
            update={"metadata": {**process.metadata, "life_cycle_stage": stages[process.code]}},
        )
        if process.code in stages
        else process.model_copy(deep=True)
        for process in system.processes
    ]
    return system.model_copy(update={"processes": processes})


def staged(stages: dict[str, str | None]) -> ProductSystem:
    """The fixture's product system with the named processes carrying these stages."""
    system = fixture_system().product_system
    assert system is not None
    return _restaged(system, stages)


def test_stages_follow_the_walk_from_the_reference() -> None:
    system = staged({"widget": "use", "frame": "manufacturing"})
    assert stage_order(system) == ["use", "manufacturing"]
    from_frame = system.model_copy(update={"reference_process": "frame"})
    assert stage_order(from_frame) == ["manufacturing", "use"]


def test_a_process_the_walk_misses_follows_in_document_order() -> None:
    whole = fixture_system().product_system
    assert whole is not None
    spare = Process(
        id=uuid.uuid4(),
        code="spare",
        name="spare part",
        unit="unit",
        location="GLO",
        reference_product="spare part",
        exchanges=[
            Exchange(
                id=uuid.uuid4(),
                type="production",
                name="spare part",
                amount=1.0,
                unit="unit",
            )
        ],
    )
    extended = whole.model_copy(update={"processes": [*whole.processes, spare]})
    system = _restaged(extended, {"widget": "use", "frame": "manufacturing", "spare": "storage"})
    assert stage_order(system) == ["use", "manufacturing", "storage"]


def test_a_stage_met_twice_is_listed_once() -> None:
    system = staged({"widget": "assembly", "frame": "assembly"})
    assert stage_order(system) == ["assembly"]


def test_a_blank_stage_is_no_stage() -> None:
    for blank in ("", "  ", None):
        system = staged({"widget": blank, "frame": blank})
        assert stage_of(system.process("widget")) is None
    assert stage_of(staged({"widget": " use "}).process("widget")) == " use "
    assert stage_order(staged({"widget": "  ", "frame": ""})) == []
