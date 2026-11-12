from __future__ import annotations

import uuid

import pytest

from ecosemantic.compute.links import link_pin
from ecosemantic.compute.overrides import case_pin
from ecosemantic.compute.render import (
    BASE_CASE,
    NAMESPACE,
    dataset_id,
    product_flow_id,
    render,
)
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.refs import SystemRef
from tests.database_fixture import casing_system, device_system


def _amounts(rendered, code: str) -> dict[str, float]:
    process = next(p for p in rendered.processes if p.code == code)
    return {e.name: e.amount for e in process.exchanges}


def test_ids_derive_from_system_code_and_case() -> None:
    system = uuid.UUID("0f0e0d0c-0b0a-4908-8706-050403020100")
    assert dataset_id(system, "a", "light") == str(uuid.uuid5(NAMESPACE, f"{system}/a/light"))
    assert product_flow_id(system, "a") == str(uuid.uuid5(NAMESPACE, f"{system}/a"))


def test_each_case_renders_its_numbers_and_drops_zero_exchanges() -> None:
    system = casing_system()
    light, heavy = render(system, "light"), render(system, "heavy")
    assert _amounts(light, "assembly") == {
        "assembled casing": 1.0,
        "casing": 0.3,
        "electricity": 2.0,
    }
    assert _amounts(heavy, "assembly")["coating steel"] == pytest.approx(0.1)
    assert _amounts(heavy, "assembly")["casing"] == pytest.approx(0.8)
    assert all(e.formula is None for p in heavy.processes for e in p.exchanges)
    assert (light.case, light.pin) == ("light", case_pin(system, system.case("light")))


def test_uncertainty_follows_the_resolved_amount() -> None:
    process = next(p for p in render(casing_system(), "heavy").processes if p.code == "casing")
    steel = next(e for e in process.exchanges if e.name == "steel")
    assert steel.uncertainty is not None and steel.uncertainty.centre() == pytest.approx(1.1)


def test_a_system_without_cases_renders_its_base() -> None:
    casing = casing_system()
    device = device_system(casing)
    rendered = render(device, None)
    assert (rendered.case, rendered.pin) == (BASE_CASE, base_pin(device))


def test_a_rendered_case_and_a_link_under_it_hold_one_pin() -> None:
    system = casing_system()
    for case in (None, "light", "heavy"):
        ref = SystemRef(product_system_id=system.id, at_hash="a" * 64, case=case)
        assert render(system, case).pin == link_pin(system, ref)


def test_rendering_is_deterministic_and_an_edit_moves_pins_not_ids() -> None:
    system = casing_system()
    assert render(system, "light") == render(system, "light")
    edited = system.model_copy(deep=True)
    edited.process("casing").exchanges[2].amount = 0.07
    for case in ("light", "heavy"):
        assert render(edited, case).pin != render(system, case).pin
    renamed = system.model_copy(deep=True)
    renamed.cases[0].name = "slim"
    assert render(renamed, "heavy").pin == render(system, "heavy").pin
    assert dataset_id(system.id, "assembly", "slim") != dataset_id(system.id, "assembly", "light")
