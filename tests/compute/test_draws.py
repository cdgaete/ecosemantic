from __future__ import annotations

import math

import pytest

from ecosemantic.compute.draws import ParameterDraws
from ecosemantic.engine.montecarlo import PARAMETER_STREAM, generator, parameter_key
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Exchange, Parameter, Process, ProductSystem, Uncertainty
from ecosemantic.model.refs import BackgroundRef
from tests.conftest import uid
from tests.fixture_data import CODES, FIXTURE_DATABASE, FIXTURE_DB


def lognormal(amount: float, scale: float) -> Uncertainty:
    return Uncertainty(type="lognormal", params={"loc": math.log(amount), "scale": scale})


def drawer(spread: Uncertainty | None, value: float = 2.0) -> ProductSystem:
    """One process whose steel input reads the parameter q and whose aluminium input reads p, q
    being 2 p, which holds the value given and the distribution given."""

    def input_(name: str, ref: BackgroundRef, formula: str) -> Exchange:
        return Exchange(
            id=uid("draws-ex", name),
            type="product",
            name=name,
            amount=0.0,
            unit="kilogram",
            input=ref,
            formula=formula,
        )

    process = Process(
        id=uid("draws-act", "drawer"),
        code="drawer",
        name="drawer",
        unit="unit",
        location="GLO",
        reference_product="drawer",
        exchanges=[
            Exchange(
                id=uid("draws-ex", "production"),
                type="production",
                name="drawer",
                amount=1.0,
                unit="unit",
            ),
            input_("steel", BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), "q"),
            input_("aluminium", BackgroundRef(database=FIXTURE_DB, id=CODES["aluminium"]), "p"),
        ],
    )
    return ProductSystem(
        id=uid("draws-product_system", "drawer"),
        name="drawer",
        database=FIXTURE_DATABASE,
        processes=[process],
        reference_process="drawer",
        parameters=[
            Parameter(name="p", value=value, uncertainty=spread),
            Parameter(name="q", formula="2 * p"),
        ],
    )


def key(system: ProductSystem, name: str) -> tuple[int, int]:
    """The key a formula exchange of this system is answered under."""
    exchanges = {exchange.name: exchange for exchange in system.process("drawer").exchanges}
    return (system.id.int, exchanges[name].id.int)


def test_an_uncertain_literal_parameter_spreads_every_formula_that_reads_it() -> None:
    system = drawer(lognormal(2.0, 0.2))
    draws = ParameterDraws([system], seed=5)
    directly = [draws.amounts(k)[key(system, "aluminium")] for k in range(20)]
    through = [draws.amounts(k)[key(system, "steel")] for k in range(20)]
    assert len(set(directly)) == 20
    # q is 2 p, so the exchange reading it draws exactly twice the one reading p
    assert through == pytest.approx([2.0 * value for value in directly], rel=1e-12)


def test_a_draws_parameters_are_the_seed_and_k_alone() -> None:
    system = drawer(lognormal(2.0, 0.2))
    aluminium = key(system, "aluminium")
    first = ParameterDraws([system], seed=5)
    again = ParameterDraws([system], seed=5)
    other = ParameterDraws([system], seed=6)
    for k in range(5):
        assert first.amounts(k)[aluminium] == again.amounts(k)[aluminium]
        # the draw is the first standard normal of the parameter's own stream
        g = generator(5, (k, PARAMETER_STREAM, system.id.int, parameter_key("p")))
        assert first.amounts(k)[aluminium] == pytest.approx(
            2.0 * math.exp(0.2 * g.standard_normal())
        )
    assert [other.amounts(k)[aluminium] for k in range(5)] != [
        first.amounts(k)[aluminium] for k in range(5)
    ]


def test_a_system_without_an_uncertain_parameter_answers_nothing() -> None:
    assert ParameterDraws([drawer(None)], seed=5).amounts(0) == {}


def test_a_bounded_parameter_is_drawn_within_its_bounds() -> None:
    bounded = Uncertainty(
        type="normal", params={"loc": 2.0, "scale": 1.0, "minimum": 1.5, "maximum": 2.5}
    )
    system = drawer(bounded)
    draws = ParameterDraws([system], seed=5)
    amounts = [draws.amounts(k)[key(system, "aluminium")] for k in range(200)]
    assert all(1.5 <= value <= 2.5 for value in amounts)
    assert len(set(amounts)) > 1


def test_a_parameter_that_cannot_be_drawn_within_its_bounds_refuses_the_run_naming_it() -> None:
    hopeless = Uncertainty(
        type="lognormal",
        params={"loc": 0.0, "scale": 3.0, "minimum": 0.999, "maximum": 1.001},
    )
    # a distribution centred where the parameter stands, so that its bounds are the ones drawn
    system = drawer(hopeless, value=1.0)
    with pytest.raises(
        Invalid, match="parameter p of drawer keeps drawing outside its bounds 0.999 to 1.001"
    ):
        ParameterDraws([system], seed=5).amounts(0)
