from __future__ import annotations

import uuid

import numpy as np
import pytest

from ecosemantic.engine.calculation import Calculation
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import DemandItem, Exchange, Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef
from tests.conftest import fixture_system, split_system
from tests.engine.conftest import SMALL, small
from tests.fixture_data import CODES, FIXTURE_DB


def host() -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    return system


def with_input(ref: BackgroundRef | ElementaryFlowRef) -> ProductSystem:
    """The fixture with the widget taking one more input."""
    system = host().model_copy(deep=True)
    kind = "elementary" if isinstance(ref, ElementaryFlowRef) else "product"
    system.process("widget").exchanges.append(
        Exchange(id=uuid.uuid4(), type=kind, name="more", amount=1.0, unit="kilogram", input=ref)
    )
    return system


def test_a_system_on_another_database_is_invalid(calculation: Calculation) -> None:
    other = host().model_copy(update={"database": SMALL})
    with pytest.raises(Invalid, match="is on 'small'"):
        calculation.foreground(other, {})


def test_an_input_from_another_database_is_invalid(calculation: Calculation) -> None:
    with pytest.raises(Invalid, match="widget references database 'small'"):
        calculation.foreground(with_input(BackgroundRef(database="small", id=CODES["steel"])), {})
    with pytest.raises(Invalid, match="widget references elementary flows 'small-biosphere'"):
        calculation.foreground(
            with_input(ElementaryFlowRef(database="small-biosphere", id="co2")), {}
        )


def test_an_input_the_background_does_not_hold_is_not_found(calculation: Calculation) -> None:
    missing = f"{uuid.uuid4()}_{uuid.uuid4()}"
    with pytest.raises(NotFound, match="names background dataset"):
        calculation.foreground(with_input(BackgroundRef(database=FIXTURE_DB, id=missing)), {})
    flows = calculation.background.database.elementary_flows
    with pytest.raises(NotFound, match="names elementary flow"):
        calculation.foreground(
            with_input(ElementaryFlowRef(database=flows, id=str(uuid.uuid4()))), {}
        )


def test_a_link_to_a_system_the_calculation_was_not_given_is_not_found(
    calculation: Calculation,
) -> None:
    system = split_system()
    assert system.product_system is not None
    with pytest.raises(NotFound, match="which the calculation was not given"):
        calculation.foreground(system.product_system, {})


def test_a_link_to_a_system_at_another_hash_is_invalid(calculation: Calculation) -> None:
    system = split_system()
    assert system.product_system is not None
    [(frame_id, frame)] = system.linked.items()
    moved = frame.model_copy(update={"hash": "0" * 64})
    with pytest.raises(Invalid, match="the calculation was given"):
        calculation.foreground(system.product_system, {frame_id: moved})


def test_a_flow_no_background_activity_emits_is_computed() -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    calculation = Calculation(background)
    product_system = ProductSystem(
        id=uuid.uuid4(),
        name="noisy",
        database=SMALL,
        processes=[
            Process(
                id=uuid.uuid4(),
                code="noisy",
                name="noisy",
                unit="unit",
                location="GLO",
                reference_product="noisy",
                exchanges=[
                    Exchange(
                        id=uuid.uuid4(), type="production", name="noisy", amount=1.0, unit="unit"
                    ),
                    Exchange(
                        id=uuid.uuid4(),
                        type="elementary",
                        name="noise",
                        amount=3.0,
                        unit="kilogram",
                        input=ElementaryFlowRef(database=SMALL.elementary_flows, id="noise"),
                    ),
                ],
            )
        ],
        reference_process="noisy",
    )
    foreground = calculation.foreground(product_system, {})
    solution = calculation.solve(
        foreground, [DemandItem(ref=ForegroundRef(code="noisy"), amount=2.0)]
    )
    inventory = calculation.inventory(solution)
    amounts = dict(
        zip(
            inventory.amounts.coords["flow"].labels.tolist(),
            inventory.amounts.values().tolist(),
            strict=True,
        )
    )
    assert amounts == {"co2": 0.0, "noise": 6.0}
    assert inventory.sources == {"noise": "noisy"}


def test_a_foreground_keeps_each_exchange_as_an_entry_that_rebuilds_its_blocks(
    calculation: Calculation,
) -> None:
    system = host()
    fg = calculation.foreground(system, {})
    own = fg.entries["own"]
    assert fg.entries["own"].matrix(np.asarray(own.amounts), fg.technosphere.shape).toarray() == (
        pytest.approx(fg.technosphere.toarray())
    )
    for block, matrix in (("uses", fg.uses), ("direct", fg.direct)):
        entries = fg.entries[block]
        rebuilt = entries.matrix(np.asarray(entries.amounts), matrix.shape)
        assert rebuilt.toarray() == pytest.approx(matrix.toarray())
    widget = system.process("widget")
    steel = widget.exchanges[1]
    at = fg.entries["uses"].keys.index((system.id.int, steel.id.int))
    assert fg.entries["uses"].uncertainties[at] == steel.uncertainty
    # production enters as stated, a use of a foreground product negated
    assert sorted(zip(own.amounts, own.flipped, strict=True)) == [
        (0.25, True),
        (1.0, False),
        (1.0, False),
    ]


def test_a_foreground_solves_over_a_technosphere_it_is_given(calculation: Calculation) -> None:
    fg = calculation.foreground(host(), {})
    demand = np.array([1.0, 0.0])
    # every amount doubled halves the supply that meets the demand
    assert fg.solve_over((2 * fg.technosphere).tocsc(), demand) == pytest.approx(
        fg.solve(demand) / 2
    )
