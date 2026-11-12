"""Compare a built USLCI bundle with scores an independent computation drew from the source zips."""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.databases.checks import unnamed
from ecosemantic.databases.lists import (
    LeftOutRow,
    UnlinkedRow,
    distinct_unlinked,
    process_ids,
    read_left_out,
    top_categories,
    unlinked_mismatches,
    write_left_out,
    write_unlinked,
)
from ecosemantic.databases.profiles import refuse_mismatches, write_profile
from ecosemantic.databases.scores import (
    ratio,
    relative_differences,
    score_every_dataset,
)
from ecosemantic.databases.stopwatch import Stopwatch
from ecosemantic.databases.uslci import profile as releases
from ecosemantic.databases.uslci.profile import Profile, Validated, recorded
from ecosemantic.model import units
from ecosemantic.package.background import Import, read_background

MINIMUM_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Validation:
    """What a validation measured: the import's datasets and categories, the largest relative
    difference between its scores and the independent computation's, every mismatch, the two lists
    it holds, and the seconds each step took."""

    datasets: int
    categories: int
    largest_rel_diff: float
    mismatches: tuple[str, ...]
    unlinked: tuple[UnlinkedRow, ...]
    left_out: tuple[LeftOutRow, ...]
    seconds: dict[str, float]


def _compared_left_out(
    built: tuple[LeftOutRow, ...], path: Path | None, processes: set[str]
) -> list[str]:
    """Every exchange the build left out that the list lacks, and every list row the build did not
    write or whose process the import lacks, each named by its process, flow and exchange."""
    if path is None:
        return []
    listed = read_left_out(path)
    mine = {row.key for row in built}
    theirs = {row.key for row in listed}
    return (
        [
            f"{row.process_name} leaves out {row.flow_name} of exchange {row.exchange_id} and the "
            "left-out list lacks it"
            for row in built
            if row.key not in theirs
        ]
        + [
            f"the left-out list holds a row of {row.process_name}, which the import lacks"
            for row in listed
            if row.process_id not in processes
        ]
        + [
            f"the left-out list holds {row.process_name} leaving out {row.flow_name} of exchange "
            f"{row.exchange_id}, which the build did not"
            for row in listed
            if row.process_id in processes and row.key not in mine
        ]
    )


def _compared(
    processes: set[str],
    rows: tuple[UnlinkedRow, ...],
    built: Sequence[LeftOutRow],
    unlinked: Path | None,
    left_out: Path | None,
) -> tuple[str, ...]:
    """Every unlinked input and every left-out exchange that the import and the build do not hold
    alike with the two lists named, each difference named; a list not named is not compared."""
    return tuple(
        unlinked_mismatches(rows, unlinked, processes)
        + _compared_left_out(tuple(built), left_out, processes)
    )


def list_mismatches(
    imported: Import, built_left_out: Sequence[LeftOutRow], profile: Profile
) -> tuple[str, ...]:
    """Every unlinked input and every left-out exchange that the import and the build do not hold
    alike with the two lists the profile names, each difference named; a list the profile names but
    the release has not recorded is not compared."""
    return _compared(
        process_ids(imported),
        distinct_unlinked(imported, {}),
        built_left_out,
        recorded(profile.unlinked),
        recorded(profile.left_out),
    )


def _independent(path: Path) -> dict[tuple[str, str, str], tuple[float, str]]:
    """The scores another computation wrote, one per dataset code, method and category, with the
    unit each is per."""
    with path.open(newline="", encoding="utf-8") as read:
        return {
            (row["code"], row["method"], row["category"]): (float(row["score"]), row["unit"])
            for row in csv.DictReader(read)
        }


def _group(key: tuple[str, str, str]) -> str:
    """A score's group: the method and the category it is scored under."""
    return repr(key[1:])


def _converted(
    core: dict[tuple[str, str, str], float],
    scored: dict[tuple[str, str, str], tuple[float, str]],
    declared: dict[str, str],
) -> tuple[dict[tuple[str, str, str], float], list[str]]:
    """The core's scores per one unit of the unit the other computation scored in, and every
    dataset whose declared unit is of another quantity than that one."""
    found: dict[tuple[str, str, str], float] = {}
    found_mismatches: list[str] = []
    for key, ours in core.items():
        if key not in scored:
            found[key] = ours
            continue
        unit = scored[key][1]
        factor = ratio(declared[key[0]], unit)
        if factor is None:
            stored = units.by_name(declared[key[0]])
            reference = units.by_symbol(unit)
            found_mismatches.append(
                f"{key[0]} under {key[2]}: the core scores it per {stored.name}, the independent "
                f"computation per {reference.name}, units of different quantities"
            )
            continue
        found[key] = ours * factor
    return found, found_mismatches


def _differences(
    core: dict[tuple[str, str, str], float],
    independent: dict[tuple[str, str, str], float],
    tolerance: float | None,
) -> tuple[float, list[str]]:
    """The largest relative difference between two computations' scores, and every pair beyond the
    tolerance, each naming the dataset, the category and both scores; a dataset or a category only
    one side scores is a mismatch."""
    differences = relative_differences(core, independent, group=_group)
    found: list[str] = []
    for method, category in sorted({key[1:] for key in core} | {key[1:] for key in independent}):
        mine = {code for code, m, c in core if (m, c) == (method, category)}
        theirs = {code for code, m, c in independent if (m, c) == (method, category)}
        if not mine or not theirs:
            scored = "the core" if mine else "the independent computation"
            found.append(f"{method}, {category}: only {scored} scores it")
            continue
        for code in sorted(mine | theirs):
            if code not in theirs:
                found.append(f"{code} under {category}: only the core scores it")
                continue
            if code not in mine:
                found.append(f"{code} under {category}: only the independent computation scores it")
                continue
            difference = differences[(code, method, category)]
            if tolerance is not None and difference > tolerance:
                found.append(
                    f"{code} under {category}: the core scores {core[(code, method, category)]!r}, "
                    f"the independent computation "
                    f"{independent[(code, method, category)]!r}, {difference:.3e} apart"
                )
    return max(differences.values(), default=0.0), found


def validate(
    bundle: Path,
    *,
    independent: Path,
    built_left_out: Path,
    unlinked: Path | None,
    left_out: Path | None,
    tolerance: float | None,
    compiled: Path | None = None,
    profile: Profile | None = None,
) -> Validation:
    """Read a bundle, compare its unlinked inputs and its left-out rows with the two lists a profile
    holds, compile it for the engine, save and load it, and compare the cradle-to-gate score of one
    unit of every dataset under every category with the independent computation's.

    The two lists are the ones a profile names when it is given, and the paths a caller passes
    otherwise. The engine scores one unit of the unit each dataset's product is declared in; the
    independent computation one unit of its flow's reference unit, so the core's score is converted
    through the core's unit table before the two meet, and a dataset whose declared unit is of
    another quantity
    than that one is a mismatch naming both. Two scores of a category then agree when both are at
    most 1e-12 of the independent computation's largest in the category; otherwise their difference
    is the absolute one over the larger magnitude, and a pair above the tolerance is a mismatch
    naming the dataset, the category and both scores. With no lists and no tolerance, as a profile
    ships before its first recorded run, the lists are not compared and the tolerance refuses
    nothing; what the run found is returned either way."""
    stopwatch = Stopwatch()

    imported = read_background(bundle, bundle.stem, foreground=frozenset())
    stopwatch.lap("read")
    processes = process_ids(imported)
    rows = distinct_unlinked(imported, top_categories(bundle))
    built = read_left_out(built_left_out)
    compared = (
        list_mismatches(imported, built, profile)
        if profile is not None
        else _compared(processes, rows, built, unlinked, left_out)
    )
    mismatches = unnamed(imported) + list(compared)
    stopwatch.lap("checks")
    scores = score_every_dataset(imported, name=bundle.stem, compiled=compiled)
    stopwatch.seconds |= scores.seconds
    scored = _independent(independent)
    converted, units_differ = _converted(scores.values, scored, scores.declared)
    largest, compared = _differences(
        converted, {key: score for key, (score, _unit) in scored.items()}, tolerance
    )
    stopwatch.lap("compare")
    return Validation(
        datasets=len(imported.datasets),
        categories=len(imported.methods),
        largest_rel_diff=largest,
        mismatches=tuple(mismatches + units_differ + compared),
        unlinked=rows,
        left_out=built,
        seconds=stopwatch.seconds,
    )


def _tolerance(largest: float) -> float:
    """Ten times a largest relative difference, rounded up to a power of ten, and at least 1e-9."""
    if largest <= 0:
        return MINIMUM_TOLERANCE
    return max(MINIMUM_TOLERANCE, 10.0 ** math.ceil(math.log10(largest * 10.0)))


def record(profile: Profile, validation: Validation) -> Path:
    """Write a passing run's two lists and its tolerance into the release's profile, under the
    directory the profiles ship in; refused while the run found a mismatch."""
    refuse_mismatches(validation.mismatches)
    write_unlinked(releases.RELEASES / profile.unlinked, validation.unlinked)
    write_left_out(releases.RELEASES / profile.left_out, validation.left_out)
    updated = profile.model_copy(
        update={
            "tolerance": _tolerance(validation.largest_rel_diff),
            "validated": Validated(
                datasets=validation.datasets,
                categories=validation.categories,
                largest_rel_diff_to_independent=validation.largest_rel_diff,
            ),
        }
    )
    return write_profile(updated, releases.RELEASES, profile.version)
