from __future__ import annotations

import uuid

from ecosemantic.compute.consequences import consequences
from ecosemantic.compute.links import link_pin, pins
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import (
    Exchange,
    ExchangeOverride,
    Parameter,
    Process,
    ProductSystem,
    Scenario,
)
from ecosemantic.model.refs import BackgroundRef, SystemRef
from ecosemantic.model.validation import validate
from tests.conftest import DATABASE


def _linking(target: ProductSystem, name: str) -> ProductSystem:
    link = SystemRef(product_system_id=target.id, at_hash=content_hash(target))
    process = Process(
        id=uuid.uuid5(uuid.NAMESPACE_OID, name),
        code="p",
        name=name,
        unit="unit",
        location="GLO",
        reference_product=name,
        exchanges=[
            Exchange(id=uuid.uuid4(), type="production", name=name, amount=1.0, unit="unit"),
            Exchange(
                id=uuid.uuid4(), type="product", name="in", amount=1.0, unit="unit", input=link
            ),
        ],
    )
    return ProductSystem(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        database=DATABASE,
        processes=[process],
        reference_process="p",
    )


def _at(pinned: ProductSystem, linking: list[ProductSystem]) -> dict[SystemRef, str | None]:
    """Each link's pin at the version it names, which here is `pinned`."""
    return {ref: link_pin(pinned, ref) for system in linking for ref in pins(system)}


def test_a_write_that_stales_two_scenarios_names_them(product_system: ProductSystem) -> None:
    before = product_system.model_copy(deep=True)
    second = Scenario(
        name="light",
        overrides=[
            ExchangeOverride(exchange_id=before.process("tshirt").exchanges[3].id, amount=0.0001)
        ],
        base_hash=base_pin(before),
    )
    before.scenarios.append(second)
    after = before.model_copy(deep=True)
    after.process("fabric").exchanges[2].amount = 3.0
    assert consequences(before, after, [], {}).scenarios_staled == ["light", "organic"]


def test_a_write_to_a_linked_system_names_the_systems_whose_links_fell_behind(
    product_system: ProductSystem,
) -> None:
    before = product_system
    after = before.model_copy(deep=True)
    after.process("fabric").exchanges[2].amount = 3.0
    linking = [_linking(before, "label_a"), _linking(before, "label_b")]
    found = consequences(before, after, linking, _at(before, linking)).links_behind
    assert [(link.product_system_id, link.name) for link in found] == [
        (linking[0].id, "label_a"),
        (linking[1].id, "label_b"),
    ]
    cased = before.model_copy(deep=True)
    cased.parameters.append(Parameter(name="unused", value=1.0))
    assert consequences(before, cased, linking, _at(before, linking)).links_behind != []
    renamed = before.model_copy(update={"notes": "checked"})
    assert consequences(before, renamed, linking, _at(before, linking)).links_behind == []


def test_a_write_names_a_positive_input_to_a_treatment_when_the_treatments_are_known(
    product_system: ProductSystem,
) -> None:
    ref = next(
        e.input
        for p in product_system.processes
        for e in p.exchanges
        if isinstance(e.input, BackgroundRef)
    )
    assert isinstance(ref, BackgroundRef)
    named = consequences(product_system, product_system, [], {}, treatments=frozenset({ref}))
    [issue] = [i for i in named.issues if i.case == "treatments_take_waste"]
    assert issue.code == "treatment_runs_backwards"
    unknown = consequences(product_system, product_system, [], {})
    assert "treatments_take_waste" not in {i.case for i in unknown.issues}


def test_a_write_that_leaves_no_reference_process_names_that_issue(
    product_system: ProductSystem,
) -> None:
    after = product_system.model_copy(update={"reference_process": None})
    found = consequences(product_system, after, [], {})
    # the reference is in the base pin, so clearing it also stales the scenario
    assert {i.code for i in found.issues} == {"reference_process_missing", "scenario_behind"}
    assert found.scenarios_staled == ["organic"]


def test_a_write_states_its_issues_and_leaves_their_remedies_to_validation(
    product_system: ProductSystem,
) -> None:
    after = product_system.model_copy(update={"reference_process": None})
    found = consequences(product_system, after, [], {})
    # a model still being written is told what is unfinished, not how to finish it
    assert found.issues and all("suggestion" not in i.model_dump() for i in found.issues)
    assert all(i.message for i in found.issues)
    assert all(e.suggestion for e in validate(after).errors)


def test_a_write_that_stales_nothing_answers_three_empty_lists(
    product_system: ProductSystem,
) -> None:
    after = product_system.model_copy(update={"notes": "checked"})
    label = [_linking(product_system, "label")]
    found = consequences(product_system, after, label, _at(product_system, label))
    assert (found.scenarios_staled, found.links_behind, found.issues) == ([], [], [])
    assert consequences(None, product_system, [], {}).scenarios_staled == []


def test_a_write_that_restores_the_pinned_state_leaves_no_link_behind(
    product_system: ProductSystem,
) -> None:
    linking = [_linking(product_system, "label")]
    edited = product_system.model_copy(deep=True)
    edited.process("fabric").exchanges[2].amount = 3.0
    at = _at(product_system, linking)
    assert consequences(product_system, edited, linking, at).links_behind != []
    # writing the pinned state back makes the link current again
    assert consequences(edited, product_system, linking, at).links_behind == []
