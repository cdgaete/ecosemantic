from __future__ import annotations

import uuid

from ecosemantic.geometry import (
    FOLD_AFTER,
    HEADER_HEIGHT,
    ROW_HEIGHT,
    SECTION_LABEL,
    SECTION_PADDING,
    card_size,
    ports,
    rows,
)
from ecosemantic.model.entities import Exchange, Process
from ecosemantic.model.refs import BackgroundRef


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


def test_inputs_at_zero_come_after_the_others_in_the_systems_order() -> None:
    process = _process([1.0, 0.0, 2.0])
    inputs, outputs = rows(process, {})
    assert [e.name for e in inputs] == ["i0", "i2", "i1"]
    assert [e.type for e in outputs] == ["production"]


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
