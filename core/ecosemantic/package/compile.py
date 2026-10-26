"""A background compiled for the engine from a bundle's import."""

from __future__ import annotations

from typing import cast

from ecosemantic.engine.background import Background, Factors, Rows
from ecosemantic.model.entities import Method, Uncertainty
from ecosemantic.model.refs import Database
from ecosemantic.package.background import Dataset, Import, require_linked


def _rows(entries: list[tuple[str, str, float, bool, Uncertainty | None]]) -> Rows:
    rows, columns, amounts, flipped, uncertainties = (
        zip(*entries, strict=True) if entries else ((), (), (), (), ())
    )
    return Rows(
        rows=rows, columns=columns, amounts=amounts, flipped=flipped, uncertainties=uncertainties
    )


def compile_background(imported: Import, database: Database) -> Background:
    """The engine's background of an import: a production enters its dataset's diagonal, a
    technosphere input its provider's row and its dataset's column, negated, an elementary
    exchange its flow's row, and a factor its category and flow; every row keeps its
    distribution. Invalid while an input is unlinked."""
    require_linked(imported)
    technosphere: list[tuple[str, str, float, bool, Uncertainty | None]] = []
    biosphere: list[tuple[str, str, float, bool, Uncertainty | None]] = []
    for (_, code), dataset in imported.datasets.items():
        for row in cast(list[Dataset], dataset["exchanges"]):
            kind = row["type"]
            _, target = cast(tuple[str, str], row["input"])
            entry = (
                target,
                code,
                float(cast(float, row["amount"])),
                kind == "technosphere",
                cast("Uncertainty | None", row["uncertainty"]),
            )
            (biosphere if kind == "biosphere" else technosphere).append(entry)
    methods = [Method.of(method.key, method.unit) for method in imported.methods]
    factors = [
        (method.id, flow, value)
        for method, imported_method in zip(methods, imported.methods, strict=True)
        for (_, flow), value in imported_method.factors
    ]
    categories, flows, values = zip(*factors, strict=True) if factors else ((), (), ())
    return Background.compile(
        database,
        activities=[code for _, code in imported.datasets],
        flows=[code for _, code in imported.flows],
        methods=methods,
        technosphere=_rows(technosphere),
        biosphere=_rows(biosphere),
        factors=Factors(categories=categories, flows=flows, values=values),
    )
