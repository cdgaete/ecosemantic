"""Apply a case or a scenario to a product system and return the variant to calculate."""

from __future__ import annotations

from ecosemantic.compute.parameters import materialize, refuse_zero_production
from ecosemantic.errors import Invalid, StaleScenario
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import (
    Case,
    ExchangeOverride,
    ParameterOverride,
    ProductSystem,
    Scenario,
)
from ecosemantic.model.refs import ForegroundRef


def _set_parameter(product_system: ProductSystem, name: str, value: float) -> None:
    parameter = product_system.parameter(name)
    if parameter.formula is not None:
        raise Invalid(f"parameter {name!r} is derived and cannot be set")
    parameter.value = value


def apply_case(product_system: ProductSystem, case: Case) -> ProductSystem:
    """The product system with the case's parameter values set and every formula recomputed."""
    out = product_system.model_copy(deep=True)
    for name, value in case.values.items():
        _set_parameter(out, name, value)
    return materialize(out)


def case_pin(product_system: ProductSystem, case: Case) -> str:
    """The base pin of the document the case resolves to: two cases that resolve to one document
    share it, and a change to the case's values moves it."""
    return base_pin(apply_case(product_system, case))


def stale(product_system: ProductSystem, scenario: Scenario) -> bool:
    """Whether the scenario is pinned to a base other than the product system's as it stands."""
    return scenario.base_hash != base_pin(product_system)


def apply_variant(product_system: ProductSystem, name: str) -> ProductSystem:
    """The product system with the named scenario or case applied and its formulas resolved.

    A scenario applies only while its pin is the base pin of the product system as it stands.
    """
    found = product_system.variant(name)
    if isinstance(found, Case):
        return apply_case(product_system, found)
    if stale(product_system, found):
        raise StaleScenario(name, found.base_hash, base_pin(product_system))
    return apply_scenario(product_system, found)


def apply_scenario(product_system: ProductSystem, scenario: Scenario) -> ProductSystem:
    """Parameter overrides, then materialisation, then exchange overrides."""
    out = product_system.model_copy(deep=True)
    for override in scenario.overrides:
        if isinstance(override, ParameterOverride):
            _set_parameter(out, override.name, override.value)
    out = materialize(out)
    for override in scenario.overrides:
        if not isinstance(override, ExchangeOverride):
            continue
        _, exchange = out.exchange(override.exchange_id)
        if override.amount is not None:
            exchange.formula = None
            exchange.amount = override.amount
        elif override.multiplier is not None:
            exchange.formula = None
            exchange.amount = exchange.amount * override.multiplier
        elif override.input is not None:
            if exchange.type != "product":
                raise Invalid(f"only technosphere exchanges take an input swap: {exchange.name!r}")
            if isinstance(override.input, ForegroundRef):
                out.process(override.input.code)
            exchange.input = override.input
    return refuse_zero_production(out)
