from __future__ import annotations

import uuid

from ecosemantic.geometry import (
    FOLD_AFTER,
    HEADER_HEIGHT,
    ROW_HEIGHT,
    SECTION_LABEL,
    SECTION_PADDING,
    card_size,
    folds,
    ports,
    rows,
    shown_inputs,
)
from ecosemantic.model.entities import Exchange, Process
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef
from ecosemantic.ports.types import Side


def _process(amounts: list[float]) -> Process:
    exchanges = [Exchange(id=uuid.uuid4(), type="production", name="p", amount=1.0, unit="kg")]
    exchanges += [
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name=f"i{n}",
            amount=amount,
            unit="kg",
            input=BackgroundRef(database="d", id=f"b{n}"),
        )
        for n, amount in enumerate(amounts)
    ]
    return Process(
        id=uuid.uuid4(),
        code="p",
        name="p",
        unit="kg",
        location="GLO",
        reference_product="p",
        exchanges=exchanges,
    )


def _sided(
    linked: list[float], others: list[float], outputs: int = 1
) -> tuple[Process, set[uuid.UUID], dict[str, Side]]:
    """A process whose inputs split into rows that draw an arrow and rows that draw none, and whose
    outputs are one production row and `outputs - 1` elementary rows."""
    exchanges = [Exchange(id=uuid.uuid4(), type="production", name="p", amount=1.0, unit="kg")]
    arrows: set[uuid.UUID] = set()
    for n, amount in enumerate(linked):
        found = Exchange(
            id=uuid.uuid4(),
            type="product",
            name=f"l{n}",
            amount=amount,
            unit="kg",
            input=ForegroundRef(code=f"l{n}"),
        )
        arrows.add(found.id)
        exchanges.append(found)
    for n, amount in enumerate(others):
        exchanges.append(
            Exchange(
                id=uuid.uuid4(),
                type="product",
                name=f"o{n}",
                amount=amount,
                unit="kg",
                input=BackgroundRef(database="d", id=f"b{n}"),
            )
        )
    sides: dict[str, Side] = {}
    for n in range(outputs - 1):
        ref = ElementaryFlowRef(database="d", id=f"f{n}")
        sides[ref.id] = "output"
        exchanges.append(
            Exchange(
                id=uuid.uuid4(), type="elementary", name=f"e{n}", amount=1.0, unit="kg", input=ref
            )
        )
    made = Process(
        id=uuid.uuid4(),
        code="p",
        name="p",
        unit="kg",
        location="GLO",
        reference_product="p",
        exchanges=exchanges,
    )
    return made, arrows, sides


def test_inputs_at_zero_come_after_the_others_in_the_systems_order() -> None:
    process = _process([1.0, 0.0, 2.0])
    inputs, outputs = rows(process, {})
    assert [e.name for e in inputs] == ["i0", "i2", "i1"]
    assert [e.type for e in outputs] == ["production"]


def test_an_input_that_draws_an_arrow_is_listed_before_the_others() -> None:
    made, arrows, sides = _sided([1.0, 1.0], [1.0, 0.0])
    inputs, _ = rows(made, sides, arrows)
    assert [e.name for e in inputs] == ["l0", "l1", "o0", "o1"]


def test_a_card_is_its_header_two_sections_and_its_rows() -> None:
    _, height = card_size(_process([1.0, 1.0]), {})
    # 2 inputs + 1 production row
    assert height == HEADER_HEIGHT + 2 * (2 * SECTION_PADDING + SECTION_LABEL) + 3 * ROW_HEIGHT


def test_each_input_row_is_anchored_at_its_middle_and_the_output_on_the_production_row() -> None:
    process = _process([1.0, 1.0])
    found, output = ports(process, {})
    first = HEADER_HEIGHT + SECTION_PADDING + SECTION_LABEL + ROW_HEIGHT / 2
    assert [p.y for p in found] == [first, first + ROW_HEIGHT]
    assert output == (
        HEADER_HEIGHT
        + 2 * SECTION_PADDING
        + SECTION_LABEL
        + 2 * ROW_HEIGHT
        + SECTION_PADDING
        + SECTION_LABEL
        + ROW_HEIGHT / 2
    )


def test_an_input_behind_the_fold_is_anchored_on_the_fold_row() -> None:
    process = _process([1.0] * (FOLD_AFTER + 2))
    found, _ = ports(process, {})
    fold = (
        HEADER_HEIGHT + SECTION_PADDING + SECTION_LABEL + FOLD_AFTER * ROW_HEIGHT + ROW_HEIGHT / 2
    )
    assert [p.y for p in found[FOLD_AFTER:]] == [fold, fold]


def test_a_card_keeps_every_input_that_draws_an_arrow_and_folds_the_rest() -> None:
    made, arrows, sides = _sided([1.0] * 7, [1.0] * 5)
    inputs, _ = folds(made, sides, arrows)
    assert inputs.shown == 7
    assert inputs.folded == 5
    assert inputs.shown == shown_inputs(made, sides, arrows)


def test_a_card_shows_six_input_rows_when_no_more_draw_an_arrow() -> None:
    made, arrows, sides = _sided([1.0] * 3, [1.0] * 9)
    inputs, _ = folds(made, sides, arrows)
    assert (inputs.shown, inputs.folded) == (FOLD_AFTER, 6)


def test_a_card_shows_every_arrow_at_its_own_anchor_and_the_rest_below_them() -> None:
    made, arrows, sides = _sided([1.0] * 7, [1.0] * 5)
    found, _ = ports(made, sides, arrows)
    assert len({port.y for port in found[:7]}) == 7
    fold = HEADER_HEIGHT + SECTION_PADDING + SECTION_LABEL + 7 * ROW_HEIGHT + ROW_HEIGHT / 2
    assert [port.y for port in found[7:]] == [fold] * 5


def test_a_card_folds_excess_outputs_after_the_production_row() -> None:
    made, _, sides = _sided([1.0], [], outputs=FOLD_AFTER + 3)
    _, outputs = folds(made, sides)
    assert (outputs.shown, outputs.folded) == (FOLD_AFTER, 3)
    assert [e.type for e in rows(made, sides)[1]][0] == "production"


def test_the_fold_row_takes_one_row_however_many_rows_it_hides_on_either_side() -> None:
    made, arrows, sides = _sided([1.0] * 7, [1.0] * 5, outputs=FOLD_AFTER + 3)
    inputs, outputs = folds(made, sides, arrows)
    _, height = card_size(made, sides, arrows)
    drawn = inputs.shown + 1 + outputs.shown + 1
    assert height == HEADER_HEIGHT + 2 * SECTION_LABEL + 4 * SECTION_PADDING + drawn * ROW_HEIGHT


def test_an_expanded_card_draws_every_row_of_both_sides() -> None:
    made, arrows, sides = _sided([1.0] * 7, [1.0] * 5, outputs=FOLD_AFTER + 3)
    inputs, outputs = folds(made, sides, arrows, expanded=True)
    assert (inputs.shown, inputs.folded) == (12, 5)
    assert (outputs.shown, outputs.folded) == (FOLD_AFTER + 3, 3)
    _, height = card_size(made, sides, arrows, expanded=True)
    assert height == HEADER_HEIGHT + 2 * SECTION_LABEL + 4 * SECTION_PADDING + 21 * ROW_HEIGHT


def test_an_expanded_card_anchors_every_input_row_at_its_own_height() -> None:
    made, arrows, sides = _sided([1.0] * 7, [1.0] * 5)
    found, _ = ports(made, sides, arrows, expanded=True)
    assert len({port.y for port in found}) == 12
