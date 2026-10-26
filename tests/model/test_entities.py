from __future__ import annotations

import math
import uuid

import pytest
from pydantic import ValidationError

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import (
    METADATA_KEYS,
    Exchange,
    ExchangeOverride,
    Parameter,
    Process,
    ProductSystem,
    Uncertainty,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
)


def test_fixture_project_builds(product_system: ProductSystem) -> None:
    assert len(product_system.processes) == 4
    assert sum(len(a.exchanges) for a in product_system.processes) == 17
    assert [p.name for p in product_system.parameters] == [
        "fabric_mass",
        "waste_rate",
        "elec_per_kg",
        "fibre_mass",
        "organic_share",
    ]


def test_a_case_and_a_scenario_never_share_a_name(product_system: ProductSystem) -> None:
    clashing = product_system.model_dump()
    clashing["cases"].append({"name": "organic", "values": {"fabric_mass": 0.2}})
    with pytest.raises(ValidationError, match=r"cases and scenarios share the names \['organic'\]"):
        ProductSystem.model_validate(clashing)


def test_a_scenario_switches_an_input_to_a_process_alone() -> None:
    exchange_id = uuid.uuid4()
    linked = SystemRef(product_system_id=uuid.uuid4(), at_hash="a" * 64)
    with pytest.raises(ValidationError, match="cannot switch an input to a linked system"):
        ExchangeOverride(exchange_id=exchange_id, input=linked)
    with pytest.raises(ValidationError, match="never to an elementary flow"):
        ExchangeOverride(exchange_id=exchange_id, input=ElementaryFlowRef(database="b", id="x"))
    ExchangeOverride(exchange_id=exchange_id, input=BackgroundRef(database="d", id="x"))
    ExchangeOverride(exchange_id=exchange_id, input=ForegroundRef(code="yarn"))


def test_uncertainty_requires_the_keys_of_its_type() -> None:
    Uncertainty(type="lognormal", params={"loc": 0.1, "scale": 0.2})
    with pytest.raises(ValidationError):
        Uncertainty(type="lognormal", params={"loc": 0.1})
    with pytest.raises(ValidationError):
        Uncertainty(type="uniform", params={"minimum": 2.0, "maximum": 1.0})
    with pytest.raises(ValidationError):
        Uncertainty(type="normal", params={"loc": 0.0, "scale": 0.0})
    with pytest.raises(ValidationError):
        Uncertainty(type="lognormal", params={"loc": 0.1, "scale": 0.2, "extra": 1.0})


def test_a_range_of_zero_width_is_refused_for_a_uniform_and_a_triangular() -> None:
    with pytest.raises(ValidationError, match="minimum must be less than maximum"):
        Uncertainty(type="uniform", params={"minimum": 1.0, "maximum": 1.0})
    with pytest.raises(ValidationError, match="minimum must be less than maximum"):
        Uncertainty(type="triangular", params={"minimum": 1.0, "loc": 1.0, "maximum": 1.0})
    Uncertainty(type="triangular", params={"minimum": 1.0, "loc": 1.0, "maximum": 2.0})


def test_uncertainty_scaled_follows_the_amount() -> None:
    lognormal = Uncertainty(type="lognormal", params={"loc": 0.0, "scale": 0.2}).scaled(0.001)
    assert lognormal.params == {"loc": pytest.approx(math.log(0.001)), "scale": 0.2}
    flipped = Uncertainty(type="lognormal", params={"loc": 0.0, "scale": 0.2}).scaled(-2.0)
    assert flipped.params["negative"] is True and flipped.params["loc"] == pytest.approx(
        math.log(2)
    )
    normal = Uncertainty(type="normal", params={"loc": 1.0, "scale": 0.5}).scaled(-2.0)
    assert normal.params == {"loc": -2.0, "scale": 1.0}
    uniform = Uncertainty(type="uniform", params={"minimum": 1.0, "maximum": 3.0}).scaled(-1.0)
    assert uniform.params == {"minimum": -3.0, "maximum": -1.0}
    tri = Uncertainty(type="triangular", params={"minimum": 1.0, "loc": 2.0, "maximum": 3.0})
    assert tri.scaled(3.0).params == {"minimum": 3.0, "loc": 6.0, "maximum": 9.0}


def test_uncertainty_anchored_centres_on_the_amount_and_keeps_its_spread() -> None:
    # stored for an amount of 0.03, resolved to 0.06 by a case
    lognormal = Uncertainty(type="lognormal", params={"loc": math.log(0.03), "scale": 0.2})
    assert lognormal.anchored(0.06).params == {"loc": pytest.approx(math.log(0.06)), "scale": 0.2}
    assert lognormal.anchored(-0.06).params["negative"] is True
    normal = Uncertainty(type="normal", params={"loc": 2.0, "scale": 0.5})
    assert normal.anchored(4.0).params == {"loc": 4.0, "scale": 1.0}
    tri = Uncertainty(type="triangular", params={"minimum": 1.0, "loc": 2.0, "maximum": 4.0})
    assert tri.anchored(1.0).params == {"minimum": 0.5, "loc": 1.0, "maximum": 2.0}
    uniform = Uncertainty(type="uniform", params={"minimum": 1.0, "maximum": 3.0})
    assert uniform.anchored(4.0).params == {"minimum": 2.0, "maximum": 6.0}


def test_an_uncertainty_anchored_to_zero_samples_nothing() -> None:
    lognormal = Uncertainty(type="lognormal", params={"loc": math.log(0.03), "scale": 0.2})
    assert lognormal.anchored(0.0) is None


def test_a_distribution_centred_on_zero_cannot_follow_an_amount() -> None:
    normal = Uncertainty(type="normal", params={"loc": 0.0, "scale": 0.5})
    with pytest.raises(Invalid, match="centred on 0"):
        normal.anchored(2.0)
    assert normal.anchored(0.0) is None


def test_production_exchange_carries_no_input_and_a_nonzero_amount() -> None:
    Exchange(id=uuid.uuid4(), type="production", name="p", amount=-1.0, unit="kilogram")
    with pytest.raises(ValidationError):
        Exchange(id=uuid.uuid4(), type="production", name="p", amount=0.0, unit="kilogram")
    with pytest.raises(ValidationError):
        Exchange(
            id=uuid.uuid4(),
            type="production",
            name="p",
            amount=1.0,
            unit="kilogram",
            input=BackgroundRef(database="d", id="x"),
        )


def test_biosphere_exchange_needs_a_biosphere_reference() -> None:
    with pytest.raises(ValidationError):
        Exchange(
            id=uuid.uuid4(),
            type="elementary",
            name="co2",
            amount=1.0,
            unit="kilogram",
            input=BackgroundRef(database="d", id="x"),
        )
    with pytest.raises(ValidationError):
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="co2",
            amount=1.0,
            unit="kilogram",
            input=ElementaryFlowRef(database="b", id="f"),
        )


def test_activity_metadata_always_carries_the_canonical_keys() -> None:
    a = Process(
        id=uuid.uuid4(), code="a", name="a", unit="kilogram", location="GLO", reference_product="a"
    )
    assert set(METADATA_KEYS) <= set(a.metadata)
    with pytest.raises(ValidationError):
        Process(
            id=uuid.uuid4(),
            code="bad code",
            name="a",
            unit="kilogram",
            location="GLO",
            reference_product="a",
        )


def test_parameter_takes_exactly_one_of_value_or_formula() -> None:
    Parameter(name="a", value=1.0)
    Parameter(name="b", formula="a * 2")
    with pytest.raises(ValidationError):
        Parameter(name="c")
    with pytest.raises(ValidationError):
        Parameter(name="d", value=1.0, formula="a")
    with pytest.raises(ValidationError):
        Parameter(name="Bad", value=1.0)


def test_exchange_override_takes_exactly_one_action() -> None:
    ExchangeOverride(exchange_id=uuid.uuid4(), multiplier=0.5)
    with pytest.raises(ValidationError):
        ExchangeOverride(exchange_id=uuid.uuid4(), amount=1.0, multiplier=0.5)
    with pytest.raises(ValidationError):
        ExchangeOverride(exchange_id=uuid.uuid4())


def test_project_rejects_duplicate_codes(product_system: ProductSystem) -> None:
    data = product_system.model_dump()
    data["processes"][1]["code"] = data["processes"][0]["code"]
    with pytest.raises(ValidationError):
        ProductSystem.model_validate(data)


def test_process_names_a_missing_code_as_not_found(product_system: ProductSystem) -> None:
    with pytest.raises(NotFound, match="no process 'ghost' in"):
        product_system.process("ghost")


def test_exchange_returns_its_holder_or_names_the_miss(product_system: ProductSystem) -> None:
    wanted = product_system.processes[0].exchanges[1]
    process, exchange = product_system.exchange(wanted.id)
    assert process is product_system.processes[0] and exchange is wanted
    with pytest.raises(NotFound, match="no exchange"):
        product_system.exchange(uuid.uuid4())


def test_scenario_returns_by_name_or_names_the_miss(product_system: ProductSystem) -> None:
    scenario = product_system.scenarios[0]
    assert product_system.scenario(scenario.name) is scenario
    with pytest.raises(NotFound, match="no scenario 'ghost' in"):
        product_system.scenario("ghost")


def test_case_returns_by_name_or_names_the_miss(product_system: ProductSystem) -> None:
    case = product_system.cases[0]
    assert product_system.case(case.name) is case
    with pytest.raises(NotFound, match="no case 'ghost' in"):
        product_system.case("ghost")


def test_variant_is_a_scenario_or_a_case_and_the_miss_lists_both(
    product_system: ProductSystem,
) -> None:
    scenario, case = product_system.scenarios[0], product_system.cases[0]
    assert product_system.variant(scenario.name) is scenario
    assert product_system.variant(case.name) is case
    with pytest.raises(
        NotFound, match=f"no scenario or case 'ghost' in .*{scenario.name}.*{case.name}"
    ):
        product_system.variant("ghost")


def test_parameter_returns_by_name_or_names_the_miss(product_system: ProductSystem) -> None:
    parameter = product_system.parameters[0]
    assert product_system.parameter(parameter.name) is parameter
    with pytest.raises(NotFound, match="no parameter 'ghost' in"):
        product_system.parameter("ghost")


def test_a_foreground_reference_names_no_product_system() -> None:
    with pytest.raises(ValidationError, match="product_system_id"):
        ForegroundRef.model_validate(
            {"kind": "foreground", "code": "fabric", "product_system_id": None}
        )


def test_a_process_produces_nothing_when_its_production_amount_is_zero(
    product_system: ProductSystem,
) -> None:
    yarn = product_system.model_copy(deep=True).process("yarn")
    assert yarn.produces_nothing() is False
    yarn.exchanges[0].amount = 0
    assert yarn.produces_nothing() is True


def test_a_document_carrying_staging_on_a_process_or_a_scenario_fails_to_load(
    product_system: ProductSystem,
) -> None:
    raw = product_system.model_dump()
    raw["processes"][0]["staging"] = True
    with pytest.raises(ValidationError, match="staging"):
        ProductSystem.model_validate(raw)
    raw = product_system.model_dump()
    raw["scenarios"][0]["staging"] = []
    with pytest.raises(ValidationError, match="staging"):
        ProductSystem.model_validate(raw)


def test_a_reference_process_names_a_process(product_system: ProductSystem) -> None:
    raw = product_system.model_dump()
    unset = ProductSystem.model_validate({**raw, "reference_process": None})
    assert unset.reference_process is None
    named = ProductSystem.model_validate({**raw, "reference_process": "tshirt"})
    assert named.reference_process == "tshirt"
    with pytest.raises(ValidationError, match="reference_process"):
        ProductSystem.model_validate({**raw, "reference_process": "ghost"})


def _with_link(product_system: ProductSystem, code: str, link: SystemRef) -> dict[str, object]:
    raw = product_system.model_copy(deep=True)
    raw.process(code).exchanges.append(
        Exchange(id=uuid.uuid4(), type="product", name="label", amount=1.0, unit="unit", input=link)
    )
    return raw.model_dump()


def test_a_link_is_a_pinned_product_input(
    product_system: ProductSystem,
) -> None:
    link = SystemRef(product_system_id=uuid.uuid4(), at_hash="a" * 64)
    held = ProductSystem.model_validate(_with_link(product_system, "tshirt", link))
    assert held.process("tshirt").exchanges[-1].input == link
    for code, bad, reason in (
        ("tshirt", SystemRef(product_system_id=link.product_system_id), "names no hash"),
        ("tshirt", SystemRef(product_system_id=product_system.id, at_hash="a" * 64), "itself"),
    ):
        with pytest.raises(ValidationError, match=reason):
            ProductSystem.model_validate(_with_link(product_system, code, bad))
    with pytest.raises(ValidationError, match="scenario cannot"):
        ExchangeOverride(exchange_id=uuid.uuid4(), input=link)
