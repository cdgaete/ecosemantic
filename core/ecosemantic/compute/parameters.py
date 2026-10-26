"""Materialise named parameters and exchange formulas into plain amounts, and read the cases
as a table."""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping, Sequence
from graphlib import CycleError, TopologicalSorter

from asteval import Interpreter
from asteval.astutils import ExceptionHolder
from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Case, Parameter, ProductSystem


class CaseRow(BaseModel):
    """One parameter across the cases, none where a case leaves the base value."""

    parameter: str
    values: list[float | None]


class CaseMatrix(BaseModel):
    """The cases as a table: one column per case, one row per parameter any case sets."""

    cases: list[str]
    rows: list[CaseRow]


def case_matrix(cases: Sequence[Case]) -> CaseMatrix:
    """The cases as a table, columns in case order and rows in parameter-name order."""
    touched = sorted({name for case in cases for name in case.values})
    return CaseMatrix(
        cases=[case.name for case in cases],
        rows=[
            CaseRow(parameter=name, values=[case.values.get(name) for case in cases])
            for name in touched
        ],
    )


def _interpreter() -> Interpreter:
    return Interpreter()


def _reads(formula: str, owner: str) -> set[str]:
    """The names a formula reads; Invalid for a formula that does not parse."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise Invalid(f"formula {formula!r} {owner} failed: SyntaxError: {error.msg}") from error
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _ordered(parameters: Sequence[Parameter], reserved: set[str]) -> list[Parameter]:
    """The parameters, each after every parameter its formula reads; Invalid for a formula naming
    a parameter that does not exist, and for parameters whose formulas form a cycle."""
    named = {parameter.name: parameter for parameter in parameters}
    graph: dict[str, set[str]] = {}
    for parameter in parameters:
        owner = f"of parameter {parameter.name!r}"
        reads = set() if parameter.formula is None else _reads(parameter.formula, owner)
        missing = sorted(reads - named.keys() - reserved)
        if missing:
            raise Invalid(
                f"formula {parameter.formula!r} {owner} names parameters {missing} that do not "
                "exist; set them before the formula"
            )
        graph[parameter.name] = reads & named.keys()
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        members = sorted(set(error.args[1]))
        raise Invalid(f"parameters {members} form a cycle through their formulas") from error
    return [named[name] for name in order]


def _value(formula: str, owner: str, values: Mapping[str, float], reserved: set[str]) -> float:
    """A formula's finite value over the values given."""
    interp = _interpreter()
    interp.symtable.update(values)
    result = interp(formula)
    if interp.error:
        raise Invalid(_failure(formula, owner, interp.error, set(values) | reserved))
    if not isinstance(result, int | float) or not math.isfinite(float(result)):
        raise Invalid(f"formula {formula!r} {owner} is not a finite number")
    return float(result)


def evaluate(
    parameters: list[Parameter], formulas: Mapping[str, str]
) -> tuple[dict[str, float], dict[str, float]]:
    """Parameter values in dependency order, then each formula's amount over them, keyed as
    the formulas are: by the name a refusal gives the exchange."""
    reserved = set(_interpreter().symtable)
    for parameter in parameters:
        if parameter.name in reserved:
            raise Invalid(f"parameter {parameter.name!r} shadows a builtin")
    values: dict[str, float] = {}
    for parameter in _ordered(parameters, reserved):
        if parameter.formula is not None:
            owner = f"of parameter {parameter.name!r}"
            values[parameter.name] = _value(parameter.formula, owner, values, reserved)
            continue
        value = float(parameter.value or 0.0)
        if not math.isfinite(value):
            raise Invalid(f"parameter {parameter.name!r} is not finite")
        values[parameter.name] = value
    amounts = {
        named: _value(formula, f"on exchange {named}", values, reserved)
        for named, formula in formulas.items()
    }
    return values, amounts


def _failure(formula: str, owner: str, errors: list[ExceptionHolder], known: set[str]) -> str:
    if errors[0].exc is NameError:
        names = {n.id for n in ast.walk(ast.parse(formula, mode="eval")) if isinstance(n, ast.Name)}
        missing = sorted(names - known)
        return (
            f"formula {formula!r} {owner} names parameters {missing} that do not exist; set "
            "them before the formula"
        )
    detail = "; ".join(_plain(err) for err in errors)
    return f"formula {formula!r} {owner} failed: {detail}"


def _plain(error: ExceptionHolder) -> str:
    name = error.exc.__name__ if isinstance(error.exc, type) else str(error.exc)
    last = str(error.msg).strip().splitlines()[-1]
    return last if last.startswith(name) else f"{name}: {last}"


def refuse_zero_production(product_system: ProductSystem) -> ProductSystem:
    """The product system as given, or Invalid naming every process that produces nothing."""
    empty = sorted(a.code for a in product_system.processes if a.produces_nothing())
    if empty:
        raise Invalid(f"the production of {empty} evaluates to zero")
    return product_system


def materialize(product_system: ProductSystem) -> ProductSystem:
    """A copy of the product system with every formula-driven exchange amount recomputed.

    A production amount that evaluates to zero is refused, so nothing materialised is unsolvable.
    """
    out = product_system.model_copy(deep=True)
    named = {out.exchange_named(e.id): e for a in out.processes for e in a.exchanges if e.formula}
    _, amounts = evaluate(out.parameters, {n: e.formula for n, e in named.items() if e.formula})
    for name, amount in amounts.items():
        named[name].amount = amount
    return refuse_zero_production(out)
