"""What the source prepares for an install held to the profile's lists, and its access notices."""

from __future__ import annotations

from pathlib import Path

import independent_scores
import pytest

from ecosemantic.databases.uslci import profile as releases
from ecosemantic.databases.uslci.build import build
from ecosemantic.databases.uslci.setup import notices, prepare
from ecosemantic.databases.uslci.validate import validate
from ecosemantic.errors import Invalid
from ecosemantic.ports.types import InstallProgress
from tests.databases.uslci.install_fixture import (
    INVENTORY_COMMIT,
    INVENTORY_GROUP,
    INVENTORY_NAME_ON_SERVER,
    METHOD_COMMIT,
    METHOD_GROUP,
    METHOD_NAME_ON_SERVER,
    VERSION,
    fixture_release,
    left_out_rows,
    unlinked_rows,
)
from tests.databases.uslci_fixture import EXPECTED, INVENTORY_NAME, write_inventory


def _release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    drop_unlinked: bool = False,
    drop_left_out: bool = False,
) -> tuple[object, object]:
    """The fixture's stub server and profile, with their lists recorded in a temporary profiles
    directory, one row shorter when asked."""
    server, profile, recorded = fixture_release(
        tmp_path, drop_unlinked=drop_unlinked, drop_left_out=drop_left_out
    )
    monkeypatch.setattr(releases, "RELEASES", recorded)
    return server, profile


def test_the_notices_are_counted_as_the_datasets_carry_them(tmp_path: Path) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    found = notices(inventory)
    assert [(notice.text, notice.datasets) for notice in found] == list(EXPECTED["notices"])


def test_notices_count_over_every_inventory(tmp_path: Path) -> None:
    first = write_inventory(tmp_path / INVENTORY_NAME)
    second = write_inventory(tmp_path / "baseline-inventory.zip")
    found = notices(first, second)
    assert [(notice.text, notice.datasets) for notice in found] == [
        (text, 2 * count) for text, count in EXPECTED["notices"]
    ]


def test_prepare_reports_its_steps_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile = _release(tmp_path, monkeypatch)
    reported: list[InstallProgress] = []

    prepare(profile, server, tmp_path / "work", reported.append)

    assert [progress.step for progress in reported] == [
        "downloading",
        "downloaded",
        "building",
        "reading",
        "checking",
    ]
    assert reported[1].count == sum(path.stat().st_size for path in server.files.values())


def test_prepare_answers_the_import_with_its_unlinked_inputs_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile = _release(tmp_path, monkeypatch)
    prepared = prepare(profile, server, tmp_path / "work", lambda _: None)
    assert prepared.bundle == tmp_path / "work" / f"uslci-{VERSION}.zip"
    assert prepared.bundle.is_file()
    assert prepared.imported.unlinked == []
    assert prepared.unlinked == unlinked_rows()
    assert [
        (record.flow, record.amount, record.unit, record.reason) for record in prepared.dropped
    ] == [("imported part", 1.0, "kilogram", "no process produces it")] * 3 + [
        ("electricity", 1.0, "megajoule", "several processes produce it")
    ] * 2
    assert len({record.dataset for record in prepared.dropped}) == 5
    assert prepared.pins == (profile.inventory, *profile.methods)
    assert [notice.text for notice in prepared.notices] == [
        text for text, _count in EXPECTED["notices"]
    ]
    assert len(prepared.imported.datasets) == EXPECTED["bundle"]["datasets"]


def test_an_unlinked_input_outside_the_list_stops_prepare_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile = _release(tmp_path, monkeypatch, drop_unlinked=True)
    with pytest.raises(Invalid) as refused:
        prepare(profile, server, tmp_path / "work", lambda _: None)
    row = unlinked_rows()[0]
    assert f"{row.process_name} takes {row.flow_name} and the unlinked list lacks it" in str(
        refused.value
    )


def test_a_left_out_exchange_outside_the_list_stops_prepare_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile = _release(tmp_path, monkeypatch, drop_left_out=True)
    with pytest.raises(Invalid) as refused:
        prepare(profile, server, tmp_path / "work", lambda _: None)
    row = left_out_rows()[0]
    assert (
        f"{row.process_name} leaves out {row.flow_name} of exchange {row.exchange_id} and the "
        "left-out list lacks it" in str(refused.value)
    )


def test_validate_compares_the_lists_a_profile_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile = _release(tmp_path, monkeypatch, drop_unlinked=True)
    inventory = server.files[(INVENTORY_GROUP, INVENTORY_NAME_ON_SERVER, INVENTORY_COMMIT)]
    method = server.files[(METHOD_GROUP, METHOD_NAME_ON_SERVER, METHOD_COMMIT)]
    work = tmp_path / "work"
    built = build(inventory, (method,), version=VERSION, out_dir=work)
    assert (
        independent_scores.main(
            [
                "--inventory",
                str(inventory),
                "--method",
                str(method),
                "--left-out",
                str(work / f"left-out-{VERSION}.csv"),
                "--out",
                str(tmp_path / "independent.csv"),
                "--unlinked-out",
                str(tmp_path / "independent-unlinked.csv"),
            ]
        )
        == 0
    )
    validation = validate(
        built.bundle,
        independent=tmp_path / "independent.csv",
        built_left_out=work / f"left-out-{VERSION}.csv",
        unlinked=None,
        left_out=None,
        tolerance=None,
        profile=profile,
    )
    row = unlinked_rows()[0]
    assert validation.mismatches == (
        f"{row.process_name} takes {row.flow_name} and the unlinked list lacks it",
    )
