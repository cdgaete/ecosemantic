"""The compile-and-score path a source's validation runs, and the two rules two computations'
scores are compared by: how far apart a pair is, and what a score per one unit is per another."""

from __future__ import annotations

import dataclasses
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import numpy as np

from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.errors import Invalid
from ecosemantic.model import units
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import Database
from ecosemantic.package.background import Import
from ecosemantic.package.compile import compile_background

NEGLIGIBLE = 1e-12
K = TypeVar("K")


@dataclass(frozen=True)
class Scores:
    """One unit of every dataset's product under every category, keyed by the dataset's code, the
    method and the category; the unit each dataset's product is declared in; and the seconds
    compiling, saving, loading and scoring took."""

    values: dict[tuple[str, str, str], float]
    declared: dict[str, str]
    seconds: dict[str, float]


def score_every_dataset(imported: Import, *, name: str, compiled: Path | None = None) -> Scores:
    """Compile a bundle's import under the database `name`, save it, load it, and score one unit of
    every dataset's product under every category; the background is written under a temporary
    directory when `compiled` names none."""
    seconds: dict[str, float] = {}
    started = time.perf_counter()

    def lap(step: str) -> None:
        nonlocal started
        now = time.perf_counter()
        seconds[step] = now - started
        started = now

    database = Database(
        name=name,
        elementary_flows=imported.biosphere,
        scheme="olca",
        version=name,
        system_model="unit process",
    )
    background = compile_background(dataclasses.replace(imported, unlinked=[]), database)
    lap("compile")
    destination = (
        compiled
        if compiled is not None
        else Path(tempfile.mkdtemp(prefix="ecosemantic-scores-")) / "background"
    )
    background.save(destination)
    lap("save")
    loaded = Background.load(destination)
    calculation = Calculation(loaded)
    lap("load")
    methods = [Method.of(method.key, method.unit) for method in imported.methods]
    codes = [code for _, code in imported.datasets]
    table = np.asarray(calculation.intensities(methods).values()).reshape(len(methods), -1)
    positions: dict[str, int] = {}
    for code in codes:
        position = loaded.position("activity", code)
        if position is None:
            raise Invalid(f"dataset {code} is not in the compiled background")
        positions[code] = position
    values = {
        (code, method.tuple[1], method.tuple[2]): float(table[at, positions[code]])
        for at, method in enumerate(methods)
        for code in codes
    }
    lap("scores")
    declared = {code: str(dataset["unit"]) for (_, code), dataset in imported.datasets.items()}
    return Scores(values=values, declared=declared, seconds=seconds)


def relative_differences(
    core: Mapping[K, float], other: Mapping[K, float], *, group: Callable[[K], str]
) -> dict[K, float]:
    """Each score both sides compute, by its absolute difference over the larger of the two
    magnitudes, and zero for a pair at most 1e-12 of its group's largest magnitude in `other`, the
    published or independent side: a column the core scores thousands of times larger than the
    reference, as BAFU's Water use, would otherwise call a reference score of 0.002 equal to a
    core score of 13.8. A group's magnitude is taken over `other`'s scores in it."""
    scales: dict[str, float] = {}
    for key, value in other.items():
        name = group(key)
        scales[name] = max(scales.get(name, 0.0), abs(value))
    found: dict[K, float] = {}
    for key, ours in core.items():
        if key not in other:
            continue
        theirs = other[key]
        scale = scales[group(key)]
        if abs(ours) <= NEGLIGIBLE * scale and abs(theirs) <= NEGLIGIBLE * scale:
            found[key] = 0.0
        else:
            found[key] = abs(ours - theirs) / max(abs(ours), abs(theirs))
    return found


def ratio(declared: str, unit: str) -> float | None:
    """The factor a score per one unit of the unit `declared` names is multiplied by to become a
    score per one unit of the unit `unit` names, and nothing when the two are units of different
    quantities."""
    stored = units.by_name(declared)
    reference = units.by_symbol(unit)
    if stored.group != reference.group:
        return None
    return reference.factor / stored.factor


def per_unit(score: float, declared: str, unit: str) -> float:
    """One score per one unit of the unit `unit` names, from a score per one unit of the unit
    `declared` names."""
    factor = ratio(declared, unit)
    if factor is None:
        raise Invalid(
            f"a score per {units.by_name(declared).name} is not one per "
            f"{units.by_symbol(unit).name}: units of different quantities"
        )
    return score * factor
