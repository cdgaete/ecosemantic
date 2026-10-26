from __future__ import annotations

import pytest

from ecosemantic.compute.parameters import case_matrix, evaluate, materialize
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Case, Parameter, ProductSystem


def test_evaluate_resolves_formulas_in_dependency_order() -> None:
    e1, e2 = "first", "second"
    values, amounts = evaluate(
        [Parameter(name="b", formula="a * 2"), Parameter(name="a", value=3.0)],
        {e1: "a + b", e2: "b / 3"},
    )
    assert values == {"a": 3.0, "b": 6.0}
    assert amounts == {e1: 9.0, e2: 2.0}


def test_evaluate_rejects_cycles_unknown_names_and_shadowing() -> None:
    with pytest.raises(Invalid):
        evaluate([Parameter(name="a", formula="b"), Parameter(name="b", formula="a")], {})
    with pytest.raises(Invalid):
        evaluate([Parameter(name="a", value=1.0)], {"steel (widget) 1": "a + missing"})
    with pytest.raises(Invalid):
        evaluate([Parameter(name="sqrt", value=1.0)], {})


def test_a_chain_of_parameters_resolves_in_order_and_reads_builtin_functions() -> None:
    values, _ = evaluate(
        [
            Parameter(name="c", formula="sqrt(b)"),
            Parameter(name="b", formula="a ** 2"),
            Parameter(name="a", value=3.0),
        ],
        {},
    )
    assert values == {"a": 3.0, "b": 9.0, "c": 3.0}


def test_a_cycle_of_parameters_is_refused_naming_its_members() -> None:
    with pytest.raises(Invalid, match=r"parameters \['a', 'b'\] form a cycle"):
        evaluate([Parameter(name="a", formula="b + 1"), Parameter(name="b", formula="a * 2")], {})
    with pytest.raises(Invalid, match=r"parameters \['a'\] form a cycle"):
        evaluate([Parameter(name="a", formula="a + 1")], {})


def test_a_parameter_formula_naming_parameters_that_do_not_exist_names_them() -> None:
    with pytest.raises(Invalid) as caught:
        evaluate([Parameter(name="b", formula="a * rate")], {})
    message = str(caught.value)
    assert "of parameter 'b'" in message and "['a', 'rate']" in message
    assert "set them" in message


def test_a_parameter_formula_that_fails_names_the_parameter_and_the_error() -> None:
    with pytest.raises(Invalid, match="formula '1 / 0' of parameter 'a' failed: ZeroDivisionError"):
        evaluate([Parameter(name="a", formula="1 / 0")], {})
    with pytest.raises(Invalid, match="formula 'a \\+' of parameter 'b' failed: SyntaxError"):
        evaluate([Parameter(name="a", value=1.0), Parameter(name="b", formula="a +")], {})


def test_evaluate_rejects_non_finite_results() -> None:
    with pytest.raises(Invalid):
        evaluate([Parameter(name="a", value=1.0)], {"steel (widget) 1": "a / 0"})


def test_materialize_recomputes_formula_amounts(product_system: ProductSystem) -> None:
    edited = product_system.model_copy(deep=True)
    edited.parameters[0].value = 0.5
    out = materialize(edited)
    tshirt = out.process("tshirt")
    assert tshirt.exchanges[1].amount == 0.5
    assert tshirt.exchanges[2].amount == pytest.approx(0.75)
    assert edited.process("tshirt").exchanges[1].amount == 0.2
    assert next(p for p in out.parameters if p.name == "fibre_mass").formula is not None


def test_evaluate_names_the_parameters_a_formula_lacks() -> None:
    with pytest.raises(Invalid) as caught:
        evaluate(
            [Parameter(name="specific_energy", value=1.0)],
            {"steel (widget) 1": "1 / (specific_energy * cycle_life * dod)"},
        )
    message = str(caught.value)
    assert "['cycle_life', 'dod']" in message and "set them" in message
    assert "NameError" not in message


def test_evaluate_reports_a_syntax_error_plainly() -> None:
    with pytest.raises(Invalid) as caught:
        evaluate([Parameter(name="a", value=1.0)], {"steel (widget) 1": "a +"})
    message = str(caught.value)
    assert "SyntaxError" in message and "('" not in message


def test_the_matrix_is_one_column_per_case_and_one_row_per_parameter_a_case_sets() -> None:
    cases = [
        Case(name="lean", values={"transport_km": 80.0}),
        Case(name="heavy", values={"transport_km": 300.0, "waste_rate": 0.2}),
    ]
    matrix = case_matrix(cases)
    assert matrix.cases == ["lean", "heavy"]
    assert [row.parameter for row in matrix.rows] == ["transport_km", "waste_rate"]
    assert matrix.rows[0].values == [80.0, 300.0]
    # blank where a case leaves the base value
    assert matrix.rows[1].values == [None, 0.2]


def test_no_cases_is_an_empty_matrix() -> None:
    matrix = case_matrix([])
    assert matrix.cases == [] and matrix.rows == []


def test_materialize_refuses_a_production_amount_of_zero(product_system: ProductSystem) -> None:
    system = product_system.model_copy(deep=True)
    system.process("yarn").exchanges[0].amount = 0
    with pytest.raises(Invalid, match="yarn"):
        materialize(system)


def test_a_formula_refusal_names_the_exchange_by_its_flow_and_process(
    product_system: ProductSystem,
) -> None:
    broken = product_system.model_copy(deep=True)
    elec = broken.process("tshirt").exchanges[2]
    elec.formula = "elec_per_kg * absent"
    with pytest.raises(Invalid) as caught:
        materialize(broken)
    assert f"sewing electricity (cotton t-shirt, assembled) {elec.id}" in str(caught.value)
