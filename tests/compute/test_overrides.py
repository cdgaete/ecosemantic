from __future__ import annotations

import uuid

import pytest

from ecosemantic.compute.edits import patch_product_system
from ecosemantic.compute.overrides import apply_case, apply_scenario, apply_variant, case_pin
from ecosemantic.errors import Invalid, NotFound, StaleScenario
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import (
    Case,
    ExchangeOverride,
    ParameterOverride,
    ProductSystem,
    Scenario,
)
from ecosemantic.model.refs import BackgroundRef, ForegroundRef
from tests.conftest import ORGANIC


def test_case_sets_parameters_and_materialises(product_system: ProductSystem) -> None:
    out = apply_case(product_system, product_system.cases[0])
    assert next(p.value for p in out.parameters if p.name == "fabric_mass") == 0.15
    assert out.process("tshirt").exchanges[1].amount == 0.15
    assert out.process("tshirt").exchanges[2].amount == pytest.approx(0.225)


def test_case_rejects_unknown_or_derived_parameter(product_system: ProductSystem) -> None:
    with pytest.raises(NotFound):
        apply_case(
            product_system, product_system.cases[0].model_copy(update={"values": {"nothing": 1.0}})
        )
    with pytest.raises(Invalid):
        apply_case(
            product_system,
            product_system.cases[0].model_copy(update={"values": {"fibre_mass": 1.0}}),
        )


def test_scenario_applies_parameter_then_exchange_overrides(product_system: ProductSystem) -> None:
    out = apply_scenario(product_system, product_system.scenarios[0])
    assert next(p.value for p in out.parameters if p.name == "waste_rate") == 0.05
    assert out.process("tshirt").exchanges[2].amount == pytest.approx(0.15)
    assert out.process("yarn").exchanges[1].input == ORGANIC
    assert product_system.process("yarn").exchanges[1].input != ORGANIC


def test_scenario_swaps_an_input_to_an_ordinary_foreground_process(
    product_system: ProductSystem,
) -> None:
    scenario = Scenario(
        name="organic_yarn",
        overrides=[
            ExchangeOverride(
                exchange_id=product_system.process("fabric").exchanges[1].id,
                input=ForegroundRef(code="organic_yarn"),
            )
        ],
    )
    out = apply_scenario(product_system, scenario)
    assert out.process("fabric").exchanges[1].input == ForegroundRef(code="organic_yarn")


def test_scenario_rejects_bad_targets(product_system: ProductSystem) -> None:
    with pytest.raises(NotFound):
        apply_scenario(
            product_system,
            Scenario(name="x", overrides=[ExchangeOverride(exchange_id=uuid.uuid4(), amount=1.0)]),
        )
    with pytest.raises(Invalid):
        apply_scenario(
            product_system,
            Scenario(
                name="x",
                overrides=[
                    ExchangeOverride(
                        exchange_id=product_system.process("tshirt").exchanges[4].id,
                        input=BackgroundRef(database="d", id="x"),
                    )
                ],
            ),
        )
    with pytest.raises(Invalid):
        apply_scenario(
            product_system,
            Scenario(name="x", overrides=[ParameterOverride(name="fibre_mass", value=1.0)]),
        )


def test_variant_applies_a_pinned_scenario_or_a_case(product_system: ProductSystem) -> None:
    stored = product_system.model_copy(deep=True, update={"hash": content_hash(product_system)})
    scenario = stored.scenarios[0]
    scenario.base_hash = base_pin(stored)
    varied = apply_variant(stored, scenario.name)
    assert varied == apply_scenario(stored, scenario)
    case = stored.cases[0]
    assert apply_variant(stored, case.name) == apply_case(stored, case)
    with pytest.raises(NotFound):
        apply_variant(stored, "nothing")


def test_variant_refuses_a_scenario_pinned_to_another_state(product_system: ProductSystem) -> None:
    stored = product_system.model_copy(deep=True, update={"hash": content_hash(product_system)})
    stored.scenarios[0].base_hash = "0" * 64
    with pytest.raises(StaleScenario) as caught:
        apply_variant(stored, stored.scenarios[0].name)
    assert (caught.value.pinned, caught.value.at) == ("0" * 64, base_pin(stored))
    # what to do about it is the surface's to say: a tool can rebase, a folder cannot
    assert "rebase_scenario" not in str(caught.value)


def test_scenario_swap_to_a_missing_foreground_process_is_refused(
    product_system: ProductSystem,
) -> None:
    exchange_id = product_system.process("fabric").exchanges[1].id
    ghost = ExchangeOverride(exchange_id=exchange_id, input=ForegroundRef(code="ghost"))
    with pytest.raises(NotFound):
        apply_scenario(product_system, Scenario(name="ghost", overrides=[ghost]))


def test_a_scenario_that_zeroes_a_production_amount_is_refused(
    product_system: ProductSystem,
) -> None:
    production = product_system.process("fabric").exchanges[0]
    for override in (
        ExchangeOverride(exchange_id=production.id, multiplier=0),
        ExchangeOverride(exchange_id=production.id, amount=0),
    ):
        with pytest.raises(Invalid, match="fabric"):
            apply_scenario(product_system, Scenario(name="empty", overrides=[override]))


def test_a_case_that_drives_a_production_formula_to_zero_is_refused(
    product_system: ProductSystem,
) -> None:
    system = product_system.model_copy(deep=True)
    system.process("tshirt").exchanges[0].formula = "fabric_mass"
    with pytest.raises(Invalid, match="tshirt"):
        apply_case(system, Case(name="none", values={"fabric_mass": 0.0}))


def test_a_process_that_produces_nothing_is_refused(product_system: ProductSystem) -> None:
    system = product_system.model_copy(deep=True)
    system.process("organic_yarn").exchanges[0].amount = 0
    with pytest.raises(Invalid, match="organic_yarn"):
        apply_case(system, system.cases[0])


def test_setting_the_reference_process_stales_the_scenarios(
    product_system: ProductSystem,
) -> None:
    system = product_system.model_copy(deep=True)
    system.hash = content_hash(system)
    system.scenarios[0].base_hash = base_pin(system)
    apply_variant(system, "organic")
    moved = patch_product_system(system, reference_process="fabric")
    moved.hash = content_hash(moved)
    assert moved.hash != system.hash
    with pytest.raises(StaleScenario):
        apply_variant(moved, "organic")


def test_a_case_pin_is_the_document_the_case_resolves_to(product_system: ProductSystem) -> None:
    small = product_system.case("small")
    same = Case(name="also_small", values={"fabric_mass": 0.15})
    assert case_pin(product_system, small) == case_pin(product_system, same)
    assert case_pin(product_system, small) != case_pin(product_system, product_system.case("large"))
    at_rest = Case(name="at_rest", values={"fabric_mass": 0.2})
    assert case_pin(product_system, at_rest) == base_pin(product_system)


def test_a_scenario_applies_while_its_pin_is_the_base_as_it_now_stands(
    product_system: ProductSystem,
) -> None:
    system = product_system.model_copy(deep=True)
    system.scenarios[0].base_hash = base_pin(system)
    system.hash = content_hash(system)
    for edit in (
        lambda s: s.cases.append(Case(name="medium", values={"fabric_mass": 0.2})),
        lambda s: s.cases[0].values.update(fabric_mass=0.1),
        lambda s: s.cases.pop(),
    ):
        cased = system.model_copy(deep=True)
        edit(cased)
        cased.hash = content_hash(cased)
        assert cased.hash != system.hash
        apply_variant(cased, "organic")
    edited = system.model_copy(deep=True)
    edited.process("fabric").exchanges[2].amount = 3.0
    edited.hash = content_hash(edited)
    with pytest.raises(StaleScenario) as caught:
        apply_variant(edited, "organic")
    assert (caught.value.pinned, caught.value.at) == (
        system.scenarios[0].base_hash,
        base_pin(edited),
    )
