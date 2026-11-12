"""The two rules a source's validation compares two computations' scores by: how far apart a pair
is, and what a score per one unit is per another."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ecosemantic.databases.scores import (
    per_unit,
    relative,
    relative_differences,
    score_every_dataset,
)
from ecosemantic.engine.background import Background
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.package.background import read_background
from tests.openlca_fixture import NAME, build_package

Key = tuple[str, str]
SAME = ("small", "one group")
BIG = ("large", "one group")
OTHER = ("small", "another group")


def _group(key: Key) -> str:
    """The group a score belongs to."""
    return key[1]


def test_two_scores_negligible_against_their_group_are_equal() -> None:
    differences = relative_differences({SAME: 0.0, BIG: 1e6}, {SAME: 1e-9, BIG: 1e6}, group=_group)
    assert differences == {SAME: 0.0, BIG: 0.0}


def test_a_pair_differs_by_its_absolute_difference_over_the_larger_magnitude() -> None:
    differences = relative_differences({SAME: 1.0, BIG: 1.0}, {SAME: 2.0}, group=_group)
    assert differences == {SAME: 0.5}


def test_scores_of_different_groups_are_measured_apart() -> None:
    differences = relative_differences(
        {SAME: 0.0, OTHER: 0.0, BIG: 1e6}, {SAME: 1e-9, OTHER: 1e-9, BIG: 1e6}, group=_group
    )
    assert differences == {SAME: 0.0, OTHER: 1.0, BIG: 0.0}


def test_the_scale_is_the_reference_s_largest() -> None:
    differences = relative_differences(
        {SAME: 5.0, BIG: 1e13}, {SAME: 0.002, BIG: 1e9}, group=_group
    )
    assert differences[SAME] == pytest.approx((5.0 - 0.002) / 5.0)
    assert differences[SAME] > 0.99


def test_one_rule_answers_the_pairs_the_three_comparisons_meet() -> None:
    pairs = [(0.0, 1e-13), (0.0, 0.0), (2.0, 1.0), (1.0, 1e-13), (1.0, 1.0 + 1e-6)]
    ours = np.array([pair[0] for pair in pairs])
    theirs = np.array([pair[1] for pair in pairs])
    measured = relative(ours, theirs, 1.0)
    assert measured == pytest.approx([0.0, 0.0, 0.5, 1.0, 1e-6], rel=1e-5)
    assert relative(np.array([0.0]), np.array([1e-300]), 0.0) == pytest.approx([1.0])

    keys = list(range(len(pairs)))
    differences = relative_differences(
        dict(zip(keys, ours.tolist(), strict=True)),
        dict(zip(keys, theirs.tolist(), strict=True)),
        group=lambda key: "one group",
    )
    assert [differences[key] for key in keys] == pytest.approx(measured.tolist(), rel=1e-5)


def test_a_score_converts_between_kilowatt_hours_and_megajoules_by_3_6() -> None:
    assert per_unit(1.0, "megajoule", "kWh") == pytest.approx(3.6)
    assert per_unit(3.6, "kilowatt hour", "MJ") == pytest.approx(1.0)


def test_a_score_per_mass_is_not_one_per_energy() -> None:
    with pytest.raises(Invalid) as refused:
        per_unit(1.0, "kilogram", "MJ")
    message = str(refused.value)
    assert "kilogram" in message
    assert "megajoule" in message


def test_a_dataset_the_compiled_background_lacks_is_not_found_naming_the_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imported = read_background(
        build_package(tmp_path / "fixture.zip"), NAME, foreground=frozenset()
    )
    left_out = next(iter(imported.datasets))
    position = Background.position

    def position_lacking(self: Background, kind: str, label: str) -> int | None:
        return None if label == left_out[1] else position(self, kind, label)

    monkeypatch.setattr(Background, "position", position_lacking)
    with pytest.raises(NotFound) as raised:
        score_every_dataset(imported, name=NAME)
    assert str(raised.value).startswith(
        f"the import names background dataset {left_out[1]!r}, which {NAME!r} does not hold"
    )
