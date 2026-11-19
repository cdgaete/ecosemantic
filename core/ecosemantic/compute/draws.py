"""Each draw's parameter values, and the amount of every formula exchange that reads them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from typing import NamedTuple

import numpy as np

from ecosemantic.compute.parameters import evaluate, uncertain_reads
from ecosemantic.engine.background import Exchanges
from ecosemantic.engine.montecarlo import PARAMETER_STREAM, generator, parameter_key, sampled
from ecosemantic.model.entities import Parameter, ProductSystem
from ecosemantic.ports.types import DrawnCount


class _Space(NamedTuple):
    """One system ready to draw from: the document, each formula exchange's formula under the name
    `evaluate` answers it by, and that name's exchange id."""

    document: ProductSystem
    formulas: dict[str, str]
    ids: dict[str, int]


def _space(system: ProductSystem) -> _Space:
    """A system's formula exchanges, keyed as `evaluate` answers them and by their ids."""
    formulas: dict[str, str] = {}
    ids: dict[str, int] = {}
    for process in system.processes:
        for exchange in process.exchanges:
            if exchange.formula is None:
                continue
            named = system.exchange_named(exchange.id)
            formulas[named] = exchange.formula
            ids[named] = exchange.id.int
    return _Space(document=system, formulas=formulas, ids=ids)


class ParameterDraws:
    """The amounts a draw gives the formula exchanges of the systems given, keyed as
    `Entries.keys`: each uncertain literal parameter sampled from a stream of its own, keyed by
    the draw, the system and the parameter's name, and every formula, of a parameter and of an
    exchange, evaluated over the values drawn. A system without an uncertain literal parameter
    answers nothing, so a model that states no distribution draws what it draws without one."""

    def __init__(self, systems: Sequence[ProductSystem], seed: int) -> None:
        self._seed = seed
        self._reached = tuple(systems)
        self._spaces = [
            _space(system)
            for system in self._reached
            if any(parameter.uncertainty is not None for parameter in system.parameters)
        ]

    def counted(self, sampled_keys: Set[tuple[int, int]]) -> DrawnCount:
        """How many literal parameters the systems state, how many carry a distribution, and how
        many of those a draw reaches: a parameter is drawn when it carries a distribution and an
        exchange the run samples reads it, keyed as `amounts` keys them."""
        there = carried = drawn = 0
        for system in self._reached:
            literal = [parameter for parameter in system.parameters if parameter.formula is None]
            uncertain = [parameter for parameter in literal if parameter.uncertainty is not None]
            there += len(literal)
            carried += len(uncertain)
            reads = uncertain_reads(system)
            for parameter in uncertain:
                if any(
                    (system.id.int, exchange_id.int) in sampled_keys
                    for exchange_id, names in reads.items()
                    if parameter.name in names
                ):
                    drawn += 1
        return DrawnCount(there=there, carried=carried, drawn=drawn)

    def amounts(self, k: int) -> Mapping[tuple[int, int], float]:
        """Each system's formula exchanges at draw k, keyed by its system's and its exchange's
        ids."""
        answered: dict[tuple[int, int], float] = {}
        for space in self._spaces:
            values = {
                parameter.name: self._drawn(space, parameter, k)
                for parameter in space.document.parameters
                if parameter.formula is None
            }
            parameters = [
                parameter
                if parameter.formula is not None
                else parameter.model_copy(update={"value": values[parameter.name]})
                for parameter in space.document.parameters
            ]
            _, amounts = evaluate(parameters, space.formulas)
            for named, amount in amounts.items():
                answered[(space.document.id.int, space.ids[named])] = amount
        return answered

    def _drawn(self, space: _Space, parameter: Parameter, k: int) -> float:
        """One literal parameter's value at draw k: its value, or its distribution as stored drawn
        from the stream of its name, within the bounds it states; Invalid naming the parameter
        where it keeps drawing outside them. The centre rule and `followed` hold the distribution
        on the value, a distribution centred on 0 included."""
        value = float(parameter.value or 0.0)
        spread = parameter.uncertainty
        if spread is None:
            return value
        g = generator(
            self._seed, (k, PARAMETER_STREAM, space.document.id.int, parameter_key(parameter.name))
        )
        rows = Exchanges.of(
            row=np.zeros(1, dtype=np.int64),
            column=np.zeros(1, dtype=np.int64),
            amounts=[value],
            flipped=[False],
            uncertainties=[spread],
        )

        def variates(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            count = int(mask.sum())
            return g.standard_normal(count), g.random(count)

        return float(
            sampled(
                rows=rows,
                variates=variates,
                held=np.zeros(1, dtype=bool),
                owners=lambda at: f"parameter {parameter.name} of {space.document.name}",
            )[0]
        )
