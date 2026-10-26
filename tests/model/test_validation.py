from __future__ import annotations

import uuid

import numpy as np
import pytest

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, ForegroundRef, SystemRef
from ecosemantic.model.validation import (
    SOLVABLE,
    Pin,
    anchors,
    credit_loops,
    reference_of,
    roots,
    undelivered,
    validate,
)
from tests.conftest import label_system


def _case(report, case_id: str) -> bool:
    return next(c.passed for c in report.cases if c.id == case_id)


def test_fixture_is_valid_for_its_reference_process(product_system: ProductSystem) -> None:
    report = validate(product_system)
    assert report.is_valid and report.target == "tshirt" and report.roots == ["tshirt"]
    assert {c.id for c in report.cases} == {
        "reference_process_set",
        "target_has_exchanges",
        "target_has_technosphere_input",
        "target_has_production",
        "production_amount_nonzero",
        "no_dangling_references",
        "no_islands",
        "same_database",
        "links_resolve",
        "links_current",
        "scenarios_current",
        "loops_deliver",
    }


def test_a_system_without_a_reference_fails_with_its_single_root_as_the_suggestion(
    product_system: ProductSystem,
) -> None:
    unset = product_system.model_copy(update={"reference_process": None})
    report = validate(unset)
    assert not report.is_valid and report.target is None
    issue = next(e for e in report.errors if e.code == "reference_process_missing")
    assert issue.suggestion == "set reference_process to 'tshirt'"
    assert not any(c.id.startswith("target_") or c.id == "no_islands" for c in report.cases)


def test_a_target_that_does_not_reach_the_system_leaves_islands(
    product_system: ProductSystem,
) -> None:
    report = validate(product_system, "fabric")
    assert not report.is_valid
    assert not _case(report, "no_islands")
    assert {e.code for e in report.errors} == {"island_activities_detected"}


def test_missing_target_raises(product_system: ProductSystem) -> None:
    with pytest.raises(NotFound):
        validate(product_system, "nothing")


def test_dangling_reference_is_reported(product_system: ProductSystem) -> None:
    broken = product_system.model_copy(deep=True)
    broken.processes[1].exchanges[1].input = ForegroundRef(code="ghost")
    report = validate(broken, "tshirt")
    assert not _case(report, "no_dangling_references")


def test_missing_production_is_reported(product_system: ProductSystem) -> None:
    broken = product_system.model_copy(deep=True)
    broken.processes[0].exchanges = [
        e for e in broken.processes[0].exchanges if e.type != "production"
    ]
    report = validate(broken, "tshirt")
    assert not _case(report, "target_has_production")


def test_the_pins_are_checked_against_what_the_store_holds(product_system: ProductSystem) -> None:
    label = label_system()
    label = label.model_copy(update={"hash": content_hash(label)})
    link = SystemRef(product_system_id=label.id, at_hash=label.hash)
    pin = base_pin(label)
    held = Pin(ref=link, name="label", current=pin, at=pin, document=label)
    report = validate(product_system, "tshirt", [held])
    assert all(_case(report, c) for c in ("links_resolve", "links_current", "same_database"))
    behind = held.model_copy(update={"current": "b" * 64})
    failed = validate(product_system, "tshirt", [behind])
    assert not _case(failed, "links_current")
    [case] = [c for c in failed.cases if c.id == "links_current"]
    assert case.detail is not None and "label" in case.detail
    missing = held.model_copy(update={"document": None})
    assert not _case(validate(product_system, "tshirt", [missing]), "links_resolve")
    elsewhere = label.model_copy(
        update={"database": label.database.model_copy(update={"name": "other"})}
    )
    moved = held.model_copy(update={"document": elsewhere})
    assert not _case(validate(product_system, "tshirt", [moved]), "same_database")


def test_reference_of_names_the_reference_process_or_refuses(
    product_system: ProductSystem,
) -> None:
    assert reference_of(product_system, "demand") == "tshirt"
    unset = product_system.model_copy(update={"reference_process": None})
    with pytest.raises(
        Invalid,
        match="has no reference process; set one with update_product_system or name a demand",
    ):
        reference_of(unset, "demand")


def test_a_process_that_consumes_its_own_product_is_still_the_root(
    product_system: ProductSystem,
) -> None:
    own = product_system.model_copy(deep=True)
    own.process("tshirt").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="cotton t-shirt",
            amount=0.1,
            unit="unit",
            input=ForegroundRef(code="tshirt"),
        )
    )
    assert roots(own) == ["tshirt"]


def _feeding(product_system: ProductSystem, *links: tuple[str, str, float]) -> ProductSystem:
    """The t-shirt system with each consumer using an amount of a provider's product."""
    fed = product_system.model_copy(deep=True)
    for consumer, provider, amount in links:
        fed.process(consumer).exchanges.append(
            Exchange(
                id=uuid.uuid4(),
                type="product",
                name=provider,
                amount=amount,
                unit="unit",
                input=ForegroundRef(code=provider),
            )
        )
    return fed


def _with_treatment(product_system: ProductSystem) -> ProductSystem:
    """The t-shirt system with a waste treatment, whose production is negative."""
    treated = product_system.model_copy(deep=True)
    treated.processes.append(
        Process(
            id=uuid.uuid4(),
            code="treatment",
            name="waste treatment",
            unit="kilogram",
            location="GLO",
            reference_product="waste",
            exchanges=[
                Exchange(id=uuid.uuid4(), type="production", name="waste", amount=-1.0, unit="kg")
            ],
        )
    )
    return treated


def test_a_loop_holding_an_input_that_runs_against_it_is_a_credit_loop(
    product_system: ProductSystem,
) -> None:
    # the t-shirt uses 0.2 fabric and the fabric 1.1 yarn
    assert credit_loops(product_system) == []
    assert credit_loops(_feeding(product_system, ("fabric", "tshirt", 2.0))) == []
    assert credit_loops(_feeding(product_system, ("fabric", "tshirt", -2.0))) == [
        ["fabric", "tshirt"]
    ]
    assert credit_loops(_feeding(product_system, ("yarn", "tshirt", -1.0))) == [
        ["fabric", "tshirt", "yarn"]
    ]
    # a process crediting its own product makes more of it; no loop runs against it
    assert credit_loops(_feeding(product_system, ("tshirt", "tshirt", -0.5))) == []


def test_waste_sent_to_a_treatment_runs_with_its_loop(product_system: ProductSystem) -> None:
    treated = _with_treatment(product_system)
    looped = _feeding(treated, ("tshirt", "treatment", -0.25), ("treatment", "tshirt", 2.0))
    assert credit_loops(looped) == []
    credited = _feeding(treated, ("tshirt", "treatment", -0.25), ("treatment", "tshirt", -2.0))
    assert credit_loops(credited) == [["treatment", "tshirt"]]


def test_anchors_are_the_reference_process_or_the_roots_while_it_is_unset(
    product_system: ProductSystem,
) -> None:
    looped = _feeding(product_system, ("fabric", "tshirt", 2.0))
    assert roots(looped) == [] and anchors(looped) == ["tshirt"]
    unset = product_system.model_copy(update={"reference_process": None})
    assert anchors(unset) == roots(unset) == ["tshirt"]


def test_a_case_the_pinned_state_does_not_carry_leaves_the_link_unresolved(
    product_system: ProductSystem,
) -> None:
    label = label_system()
    label = label.model_copy(update={"hash": content_hash(label)})
    link = SystemRef(product_system_id=label.id, at_hash=label.hash, case="ghost")
    held = Pin(ref=link, name="label", current=None, at=None, document=label)
    report = validate(product_system, "tshirt", [held])
    assert not _case(report, "links_resolve")
    # the case is gone now but was there at the pin: the link is behind
    lost = held.model_copy(update={"at": "a" * 64})
    assert not _case(validate(product_system, "tshirt", [lost]), "links_current")


def test_a_scenario_behind_the_base_fails_scenarios_current_naming_it(
    product_system: ProductSystem,
) -> None:
    assert _case(validate(product_system), "scenarios_current")
    behind = product_system.model_copy(deep=True)
    behind.scenarios[0].base_hash = "0" * 64
    report = validate(behind)
    [case] = [c for c in report.cases if c.id == "scenarios_current"]
    assert not case.passed and case.detail == "organic"
    assert "scenario_behind" in {e.code for e in report.errors}


def test_every_failing_case_fills_its_detail(product_system: ProductSystem) -> None:
    broken = product_system.model_copy(deep=True)
    broken.processes[1].exchanges[1].input = ForegroundRef(code="ghost")
    broken.scenarios[0].base_hash = "0" * 64
    broken.process("tshirt").exchanges = [
        e for e in broken.process("tshirt").exchanges if e.type != "production"
    ]
    report = validate(broken, "tshirt")
    failed = [c for c in report.cases if not c.passed]
    assert len(failed) >= 3
    assert all(c.detail for c in failed)
    assert all(c.detail is None for c in report.cases if c.passed)


def test_an_issue_names_its_case_and_the_advisory_cases_do_not_block_a_solve(
    product_system: ProductSystem,
) -> None:
    unreferenced = product_system.model_copy(update={"reference_process": None})
    assert validate(unreferenced).errors[0].case == "reference_process_set"
    assert "reference_process_set" in SOLVABLE
    assert "loops_deliver" in SOLVABLE
    assert not SOLVABLE & {
        "links_current",
        "scenarios_current",
        "no_islands",
        "target_has_production",
        "production_amount_nonzero",
    }


def _loop_issue(product_system: ProductSystem) -> str | None:
    report = validate(product_system)
    return next((e.message for e in report.errors if e.case == "loops_deliver"), None)


def test_a_loop_that_delivers_nothing_fails_loops_deliver_naming_its_processes(
    product_system: ProductSystem,
) -> None:
    # the t-shirt uses 0.2 fabric, so fabric using k t-shirts closes a loop of gain 0.2 k
    assert _loop_issue(_feeding(product_system, ("fabric", "tshirt", 2.0))) is None
    for k in (5.0, 10.0):
        message = _loop_issue(_feeding(product_system, ("fabric", "tshirt", k)))
        assert message is not None and "fabric, tshirt feed each other" in message


def test_a_process_using_more_of_its_own_product_than_it_makes_fails_loops_deliver(
    product_system: ProductSystem,
) -> None:
    assert _loop_issue(_feeding(product_system, ("tshirt", "tshirt", 0.5))) is None
    message = _loop_issue(_feeding(product_system, ("tshirt", "tshirt", 2.0)))
    assert message == "tshirt uses 2 of its own product and makes 1; it delivers none"


def test_a_loop_holding_a_credit_fails_only_when_singular(product_system: ProductSystem) -> None:
    assert _loop_issue(_feeding(product_system, ("fabric", "tshirt", -10.0))) is None
    assert undelivered(np.array([[1.0, -1.0], [-1.0, 1.0]]), credit=True) == "singular"
    assert undelivered(np.array([[1.0, -2.0], [-2.0, 1.0]]), credit=True) is None
    assert undelivered(np.array([[1.0, -2.0], [-2.0, 1.0]]), credit=False) == "short"
    assert undelivered(np.array([[1.0, -0.5], [-0.5, 1.0]]), credit=False) is None


def test_a_loop_inside_a_linked_system_fails_loops_deliver_naming_that_system(
    product_system: ProductSystem,
) -> None:
    label = label_system()
    looped = _feeding(label, (label.processes[0].code, label.processes[0].code, 2.0))
    looped = looped.model_copy(update={"hash": content_hash(looped)})
    link = SystemRef(product_system_id=looped.id, at_hash=looped.hash)
    held = Pin(ref=link, name=looped.name, current=None, at=None, document=looped)
    report = validate(product_system, "tshirt", [held])
    [issue] = [e for e in report.errors if e.case == "loops_deliver"]
    assert f"{label.processes[0].code} of {looped.name} uses 2" in issue.message


def test_a_build_other_than_the_installed_one_is_a_case(product_system: ProductSystem) -> None:
    installed = product_system.database.model_copy(update={"fingerprint": "a" * 64})
    assert "database_build" not in {c.id for c in validate(product_system).cases}
    report = validate(product_system, installed=installed)
    assert not _case(report, "database_build") and not report.is_valid
    issue = next(i for i in report.errors if i.case == "database_build")
    assert issue.code == "database_build_differs"
    assert issue.suggestion == (
        "install the build it names, or rebase_database moves it onto the installed build"
    )
    stamped = product_system.model_copy(update={"database": installed})
    assert _case(validate(stamped, installed=installed), "database_build")


def _sent_to_background(product_system: ProductSystem) -> tuple[Process, Exchange, BackgroundRef]:
    process, exchange = next(
        (p, e)
        for p in product_system.processes
        for e in p.exchanges
        if e.type == "product" and isinstance(e.input, BackgroundRef)
    )
    assert isinstance(exchange.input, BackgroundRef)
    return process, exchange, exchange.input


def _negated(product_system: ProductSystem, ref: BackgroundRef) -> ProductSystem:
    processes = [
        p.model_copy(
            update={
                "exchanges": [
                    e.model_copy(update={"amount": -e.amount, "formula": None})
                    if e.input == ref
                    else e
                    for e in p.exchanges
                ]
            }
        )
        for p in product_system.processes
    ]
    return product_system.model_copy(update={"processes": processes})


def test_a_positive_input_to_a_treatment_is_a_case(product_system: ProductSystem) -> None:
    process, exchange, ref = _sent_to_background(product_system)
    assert "treatments_take_waste" not in {c.id for c in validate(product_system).cases}
    report = validate(product_system, treatments=frozenset({ref}))
    assert not _case(report, "treatments_take_waste") and not report.is_valid
    issue = next(i for i in report.errors if i.case == "treatments_take_waste")
    senders = sorted(
        {p.code for p in product_system.processes for e in p.exchanges if e.input == ref}
    )
    assert issue.code == "treatment_runs_backwards" and issue.process_codes == senders
    assert f"{process.code} · {exchange.name} at {exchange.amount:g}" in issue.message
    assert issue.suggestion == "negate the amount: waste sent to a treatment is a negative input"
    negated = _negated(product_system, ref)
    assert _case(validate(negated, treatments=frozenset({ref})), "treatments_take_waste")
    assert _case(validate(product_system, treatments=frozenset()), "treatments_take_waste")


def test_a_positive_input_to_a_treatment_in_a_linked_state_names_its_system(
    product_system: ProductSystem,
) -> None:
    label = label_system()
    linked = product_system.model_copy(update={"hash": content_hash(product_system)})
    process, exchange, ref = _sent_to_background(linked)
    link = SystemRef(product_system_id=linked.id, at_hash=linked.hash)
    held = Pin(ref=link, name=linked.name, current=None, at=None, document=linked)
    report = validate(label, "label", [held], treatments=frozenset({ref}))
    [issue] = [e for e in report.errors if e.case == "treatments_take_waste"]
    assert f"{process.code} of {linked.name} · {exchange.name}" in issue.message
    assert issue.process_codes == []
