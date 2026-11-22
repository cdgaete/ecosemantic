"""The split of a score by life-cycle stage: the stages, their processes and their inputs."""

from __future__ import annotations

import pytest

from ecosemantic.compute.stages import by_stage
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef, ForegroundRef
from ecosemantic.ports.types import InputPart, OwnPart, OwnParts, Score
from tests.conformance.calculation import GWP_METHOD
from tests.conftest import fixture_system
from tests.fixture_data import CODES, FIXTURE_DB

STEEL = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])
ELEC = BackgroundRef(database=FIXTURE_DB, id=CODES["elec"])
PLASTIC = BackgroundRef(database=FIXTURE_DB, id=CODES["plastic"])


def staged(stages: dict[str, str | None]) -> ProductSystem:
    """The fixture's product system with each of its processes carrying the stage named here."""
    system = fixture_system().product_system
    assert system is not None
    processes = [
        process.model_copy(
            deep=True,
            update={"metadata": {**process.metadata, "life_cycle_stage": stages[process.code]}},
        )
        for process in system.processes
    ]
    return system.model_copy(update={"processes": processes})


def widget_part() -> OwnPart:
    """The widget's own part of the fixture's 2.49: direct 0.1, steel 1.39, electricity 1.0."""
    return OwnPart(
        ref=ForegroundRef(code="widget"),
        direct=0.1,
        inputs=[
            InputPart(ref=STEEL, name="steel production", location="GLO", score=1.39),
            InputPart(ref=ELEC, name="electricity production", location="GLO", score=1.0),
        ],
        score=2.49,
    )


def frame_part() -> OwnPart:
    """The frame's own part of the fixture's 1.668: a quarter of a kilogram of steel."""
    return OwnPart(
        ref=ForegroundRef(code="frame"),
        direct=0.0,
        inputs=[InputPart(ref=STEEL, name="steel production", location="GLO", score=1.668)],
        score=1.668,
    )


def own_parts(parts: list[OwnPart], total: float) -> OwnParts:
    """These own parts and the total they make."""
    return OwnParts(
        total=Score(value=total, unit=GWP_METHOD.unit, method_id=GWP_METHOD.id),
        parts=parts,
    )


def fixture_parts(widget: OwnPart | None = None, total: float = 4.158) -> OwnParts:
    """The fixture's own parts, the widget's this one and the total they make."""
    return own_parts([widget_part() if widget is None else widget, frame_part()], total)


def test_stages_partition_the_total_in_the_walk_order() -> None:
    system = staged({"widget": "assembly", "frame": "materials"})
    split = by_stage(system, fixture_parts(), cutoff=0.01)
    assert [part.stage for part in split] == ["assembly", "materials"]
    assert [part.score for part in split] == pytest.approx([2.49, 1.668])
    assert [part.fraction for part in split] == pytest.approx([2.49 / 4.158, 1.668 / 4.158])
    assert [process.ref.code for part in split for process in part.processes] == [
        "widget",
        "frame",
    ]
    assert [(process.name, process.location) for process in split[0].processes] == [
        ("widget assembly", "GLO")
    ]


def test_processes_of_one_stage_come_by_falling_magnitude() -> None:
    system = staged({"widget": "assembly", "frame": "assembly"})
    split = by_stage(system, own_parts([frame_part(), widget_part()], 4.158), cutoff=0.01)
    [assembly] = split
    assert [process.ref.code for process in assembly.processes] == ["widget", "frame"]
    assert [process.score for process in assembly.processes] == pytest.approx([2.49, 1.668])
    assert assembly.fraction == pytest.approx(1.0)


def test_processes_without_a_stage_form_the_last_part() -> None:
    one_unstaged = staged({"widget": "assembly", "frame": None})
    split = by_stage(one_unstaged, fixture_parts(), cutoff=0.01)
    assert [part.stage for part in split] == ["assembly", None]
    assert [part.score for part in split] == pytest.approx([2.49, 1.668])
    none_staged = staged({"widget": None, "frame": None})
    unstaged = by_stage(none_staged, fixture_parts(), cutoff=0.01)
    assert [part.stage for part in unstaged] == [None]
    assert [process.ref.code for process in unstaged[0].processes] == ["widget", "frame"]


def test_a_stage_none_of_whose_processes_takes_part_is_not_listed() -> None:
    system = staged({"widget": "assembly", "frame": "materials"})
    widget_only = own_parts([widget_part()], 2.49)
    assert [part.stage for part in by_stage(system, widget_only, cutoff=0.01)] == ["assembly"]


def test_inputs_under_the_cutoff_fold_into_one_remainder() -> None:
    system = staged({"widget": "assembly", "frame": "materials"})
    split = by_stage(system, fixture_parts(), cutoff=0.3)
    widget = split[0].processes[0]
    assert [(one.kind, one.name) for one in widget.inputs] == [
        ("process", "steel production"),
        ("remainder", "remainder"),
    ]
    assert [one.score for one in widget.inputs] == pytest.approx([1.39, 1.0])
    assert widget.inputs[1].ref is None and widget.inputs[1].location is None
    assert widget.direct + sum(one.score for one in widget.inputs) == pytest.approx(2.49)
    assert [one.kind for one in split[1].processes[0].inputs] == ["process"]


def test_a_credit_is_a_negative_part_and_the_split_still_sums() -> None:
    credit = InputPart(ref=PLASTIC, name="plastic production", location="GLO", score=-2.5)
    credited = widget_part().model_copy(
        update={"inputs": [*widget_part().inputs, credit], "score": -0.01}
    )
    system = staged({"widget": "assembly", "frame": "materials"})
    split = by_stage(system, fixture_parts(credited, 1.658), cutoff=0.01)
    assembly, materials = split
    assert [one.score for one in assembly.processes[0].inputs] == pytest.approx([-2.5, 1.39, 1.0])
    assert assembly.processes[0].inputs[0].score < 0
    assert assembly.fraction is not None and assembly.fraction < 0
    assert materials.fraction is not None and materials.fraction > 1
    assert sum(part.score for part in split) == pytest.approx(1.658)


def test_over_a_total_of_zero_no_part_is_a_share() -> None:
    nought = [
        part.model_copy(
            update={
                "direct": 0.0,
                "score": 0.0,
                "inputs": [one.model_copy(update={"score": 0.0}) for one in part.inputs],
            }
        )
        for part in (widget_part(), frame_part())
    ]
    system = staged({"widget": "assembly", "frame": "materials"})
    split = by_stage(system, own_parts(nought, 0.0), cutoff=0.01)
    assert [part.stage for part in split] == ["assembly", "materials"]
    for part in split:
        assert part.fraction is None
        for process in part.processes:
            assert process.fraction is None
            assert [one.fraction for one in process.inputs] == [None] * len(process.inputs)


def test_a_split_that_misses_its_total_raises() -> None:
    system = staged({"widget": "assembly", "frame": "materials"})
    with pytest.raises(Invalid, match="misses"):
        by_stage(system, fixture_parts(total=4.158 * (1 + 1e-6)), cutoff=0.01)
