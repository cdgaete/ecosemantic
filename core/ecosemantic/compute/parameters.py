"""Materialise named parameters and exchange formulas into plain amounts, and read the cases
as a table."""

from __future__ import annotations

import ast
import math
import uuid
from collections.abc import Mapping, Sequence
from graphlib import CycleError, TopologicalSorter
from typing import Final

from asteval import Interpreter
from asteval.astutils import ExceptionHolder
from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Case, Parameter, ProductSystem, Uncertainty


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


FUNCTIONS: Final[Mapping[str, object]] = {
    "abs": abs,
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "atan2": math.atan2,
    "ceil": math.ceil,
    "cos": math.cos,
    "cosh": math.cosh,
    "degrees": math.degrees,
    "exp": math.exp,
    "floor": math.floor,
    "hypot": math.hypot,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "max": max,
    "min": min,
    "pow": math.pow,
    "radians": math.radians,
    "round": round,
    "sin": math.sin,
    "sinh": math.sinh,
    "sqrt": math.sqrt,
    "tan": math.tan,
    "tanh": math.tanh,
}

CONSTANTS: Final[Mapping[str, float]] = {"pi": math.pi, "e": math.e}

CENTRE_TOLERANCE: Final = 1e-9

TAKES: Final = (
    "a formula takes numbers, parameter names, arithmetic, comparisons, a conditional and the "
    f"functions {', '.join(sorted(FUNCTIONS))}"
)

_TAKEN: Final = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Name,
    ast.expr_context,
    ast.operator,
    ast.unaryop,
    ast.boolop,
    ast.cmpop,
)


def _interpreter(values: Mapping[str, float]) -> Interpreter:
    """An interpreter that knows FUNCTIONS, CONSTANTS and the values given, and evaluates
    expressions alone: it holds no function that reads a file or looks inside an object."""
    return Interpreter(
        symtable={**FUNCTIONS, **CONSTANTS, **values}, minimal=True, config={"ifexp": True}
    )


def _held(kind: str) -> str:
    return f"holds {'an' if kind[0] in 'AEIOU' else 'a'} {kind}"


def _beyond(node: ast.AST) -> str | None:
    """What a node of a formula holds beyond what a formula takes, or none for one it takes: a
    call of anything but a name in FUNCTIONS or with a keyword, a constant that is no number,
    and every node that is not arithmetic, a comparison, a conditional or a name."""
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            return "calls what is no name"
        if node.func.id not in FUNCTIONS:
            return f"calls {node.func.id!r}"
        return f"calls {node.func.id!r} with a keyword" if node.keywords else None
    if isinstance(node, ast.Constant):
        return None if isinstance(node.value, int | float) else _held(type(node.value).__name__)
    return None if isinstance(node, _TAKEN) else _held(type(node).__name__)


def _reads(formula: str, owner: str) -> set[str]:
    """The names a formula reads; Invalid for a formula that does not parse, and for one that
    holds more than a formula takes, naming the first such thing it holds."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise Invalid(f"formula {formula!r} {owner} failed: SyntaxError: {error.msg}") from error
    for node in ast.walk(tree):
        beyond = _beyond(node)
        if beyond is not None:
            raise Invalid(f"formula {formula!r} {owner} {beyond}; {TAKES}")
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _unknown(formula: str, owner: str, missing: list[str]) -> Invalid:
    """The refusal of a formula naming parameters that do not exist."""
    return Invalid(
        f"formula {formula!r} {owner} names parameters {missing} that do not exist; set them "
        "before the formula"
    )


def _ordered(parameters: Sequence[Parameter], reserved: set[str]) -> list[Parameter]:
    """The parameters, each after every parameter its formula reads; Invalid for a formula naming
    a parameter that does not exist, and for parameters whose formulas form a cycle."""
    named = {parameter.name: parameter for parameter in parameters}
    graph: dict[str, set[str]] = {}
    for parameter in parameters:
        if parameter.formula is None:
            graph[parameter.name] = set()
            continue
        owner = f"of parameter {parameter.name!r}"
        reads = _reads(parameter.formula, owner)
        missing = sorted(reads - named.keys() - reserved)
        if missing:
            raise _unknown(parameter.formula, owner, missing)
        graph[parameter.name] = reads & named.keys()
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        members = sorted(set(error.args[1]))
        raise Invalid(f"parameters {members} form a cycle through their formulas") from error
    return [named[name] for name in order]


def _value(formula: str, owner: str, values: Mapping[str, float], reserved: set[str]) -> float:
    """A formula's finite value over the values given; Invalid for one that holds more than a
    formula takes, names a parameter that does not exist, or fails."""
    missing = sorted(_reads(formula, owner) - values.keys() - reserved)
    if missing:
        raise _unknown(formula, owner, missing)
    interp = _interpreter(values)
    result = interp(formula)
    if interp.error:
        detail = "; ".join(_plain(err) for err in interp.error)
        raise Invalid(f"formula {formula!r} {owner} failed: {detail}")
    if not isinstance(result, int | float) or not math.isfinite(float(result)):
        raise Invalid(f"formula {formula!r} {owner} is not a finite number")
    return float(result)


def evaluate(
    parameters: list[Parameter], formulas: Mapping[str, str]
) -> tuple[dict[str, float], dict[str, float]]:
    """Parameter values in dependency order, then each formula's amount over them, keyed as
    the formulas are: by the name a refusal gives the exchange."""
    reserved = set(_interpreter({}).symtable)
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


def require_centred(uncertainty: Uncertainty, value: float, owner: str) -> None:
    """Nothing where the distribution is centred on the value within a relative
    CENTRE_TOLERANCE; Invalid naming both centres otherwise, a lognormal's beside the loc that
    centres it on the value."""
    centre = uncertainty.centre()
    if math.isclose(centre, value, rel_tol=CENTRE_TOLERANCE):
        return
    loc = ""
    if uncertainty.type == "lognormal" and value != 0:
        loc = f" (loc {math.log(abs(value))!r})"
    raise Invalid(
        f"{owner} is {value!r} and its {uncertainty.type} is centred on {centre!r}; "
        f"centre it on {value!r}{loc}"
    )


def followed(uncertainty: Uncertainty | None, value: float, owner: str) -> Uncertainty | None:
    """The distribution moved onto a value a case, a scenario or an exchange's new amount
    resolved, keeping its relative spread: the distribution itself where it is centred on the
    value as it stands, none where a distribution centred elsewhere meets a value of zero, and
    Invalid naming the owner for a distribution centred on 0, which no other value follows."""
    if uncertainty is None:
        return None
    if uncertainty.centre() == value:
        return uncertainty
    if value == 0:
        return None
    if uncertainty.centre() == 0:
        raise Invalid(
            f"{owner} carries a {uncertainty.type} centred on 0 and cannot follow {value!r}; "
            f"give it a distribution centred on {value!r}, or none"
        )
    return uncertainty.anchored(value)


def _reaches(formula: str, owner: str, formulas: Mapping[str, str]) -> set[str]:
    """Every name a formula reads, and every name the formulas of those names read, in turn."""
    found: set[str] = set()
    pending = list(_reads(formula, owner))
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        if name in formulas:
            pending.extend(_reads(formulas[name], f"of parameter {name!r}"))
    return found


def uncertain_reads(system: ProductSystem) -> dict[uuid.UUID, list[str]]:
    """Each exchange whose formula reads an uncertain literal parameter, directly or through
    formula parameters, to those parameters' names, sorted."""
    uncertain = {p.name for p in system.parameters if p.uncertainty is not None}
    if not uncertain:
        return {}
    formulas: dict[str, str] = {}
    for parameter in system.parameters:
        if parameter.formula is not None:
            formulas[parameter.name] = parameter.formula
    reads: dict[uuid.UUID, list[str]] = {}
    for process in system.processes:
        for exchange in process.exchanges:
            if exchange.formula is None:
                continue
            owner = f"on exchange {system.exchange_named(exchange.id)}"
            names = _reaches(exchange.formula, owner, formulas) & uncertain
            if names:
                reads[exchange.id] = sorted(names)
    return reads


def refuse_double_spread(system: ProductSystem) -> None:
    """Nothing, or Invalid naming an exchange whose formula reads an uncertain parameter and
    which carries a distribution of its own, with the parameters it reads."""
    for exchange_id, names in uncertain_reads(system).items():
        _, exchange = system.exchange(exchange_id)
        if exchange.uncertainty is None:
            continue
        raise Invalid(
            f"exchange {system.exchange_named(exchange_id)} carries a distribution and its "
            f"formula reads the uncertain parameters {names}; an amount takes one spread: "
            "remove one of them"
        )


def refuse_unfollowed_cases(system: ProductSystem) -> None:
    """Nothing, or Invalid naming the case and the parameter for a case value the parameter's
    distribution cannot follow; a case value of 0 leaves the parameter none unless the
    distribution is centred on it."""
    for case in system.cases:
        for name, value in sorted(case.values.items()):
            parameter = system.parameter(name)
            if parameter.formula is None and parameter.uncertainty is not None:
                owner = f"parameter {name!r}, which case {case.name!r} sets,"
                followed(parameter.uncertainty, value, owner)
