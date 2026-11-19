"""EcoSemantic's revision of a publisher's release: each recorded correction applied to the record
it names, every elementary flow written canonical, and the revision carried in the manifest."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.databases.revision import read_corrections, revise
from ecosemantic.errors import Invalid
from ecosemantic.package.background import read_background
from ecosemantic.package.canonical import canonical_flow_record
from ecosemantic.package.manifest import MANIFEST, Correction, read_manifest
from tests.openlca_fixture import AIR, FLOW_IDS, NAME, build_package

NOW = datetime(2026, 1, 1, tzinfo=UTC)
VERSION = "1.0"
CORRECTED = "Elementary flows/Emission to air/high population density"
PLACED = "Elementary flows/air/high population density"
COLUMNS = "entity,id,field,published,corrected,why\n"


def _co2_correction(published: str = AIR) -> Correction:
    """The correction of the fixture's carbon dioxide from the path its publisher wrote."""
    return Correction(
        entity="Flow",
        id=FLOW_IDS["co2"],
        field="category",
        published=published,
        corrected=CORRECTED,
        why="filed under a path no rule places",
    )


def _revise(
    staged: Path, destination: Path, corrections: tuple[Correction, ...] = (), *, revision: int = 2
) -> Path:
    """Revise one staged package into `destination` as the fixture's second revision."""
    revise(
        staged,
        destination,
        name=NAME,
        version=VERSION,
        revision=revision,
        corrections=corrections,
        now=NOW,
    )
    return destination


def _revised(
    tmp_path: Path, corrections: tuple[Correction, ...] = (), *, revision: int = 2
) -> Path:
    """The fixture's package revised into `tmp_path/revised.zip`."""
    staged = build_package(tmp_path / "staged.zip")
    return _revise(staged, tmp_path / "revised.zip", corrections, revision=revision)


def _members(bundle: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(bundle) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _records(bundle: Path) -> dict[str, dict[str, object]]:
    return {
        name: json.loads(content)
        for name, content in _members(bundle).items()
        if name.startswith("flows/") and name.endswith(".json")
    }


def test_a_correction_is_applied_and_carried_in_the_manifest(tmp_path: Path) -> None:
    correction = _co2_correction()
    revised = _revised(tmp_path, (correction,))

    assert _records(revised)[f"flows/{FLOW_IDS['co2']}.json"]["category"] == PLACED
    manifest = read_manifest(revised)
    assert manifest.revision == 2
    assert manifest.corrections == [correction]


def test_a_correction_whose_published_value_no_longer_matches_fails_the_build(
    tmp_path: Path,
) -> None:
    published = "Elementary flows/Emissions to air/the publisher has moved it"
    with pytest.raises(Invalid) as refused:
        _revised(tmp_path, (_co2_correction(published),))

    assert str(refused.value) == (
        f"correction of Flow {FLOW_IDS['co2']} category: expected {published!r}, found {AIR!r}"
    )
    assert not (tmp_path / "revised.zip").exists()


def test_a_correction_of_a_record_the_release_lacks_fails_the_build(tmp_path: Path) -> None:
    correction = Correction(
        entity="Process",
        id="1a5e0dd4-3a4f-4c40-9c2b-0b8a4a4f2f11",
        field="name",
        published="a process the release does not hold",
        corrected="another name",
        why="named by a list that outlived the release",
    )
    with pytest.raises(Invalid) as refused:
        _revised(tmp_path, (correction,))

    assert str(refused.value) == (
        f"correction of Process {correction.id} name: expected {correction.published!r}, found None"
    )
    assert not (tmp_path / "revised.zip").exists()


def test_revise_writes_every_flow_canonical(tmp_path: Path) -> None:
    staged = build_package(tmp_path / "staged.zip")
    revised = _revise(staged, tmp_path / "revised.zip")

    records = _records(revised)
    assert records
    for record in records.values():
        assert record == canonical_flow_record(record)

    assert read_background(revised, NAME, foreground=frozenset()) == read_background(
        staged, NAME, foreground=frozenset()
    )


def test_revising_a_revised_bundle_changes_no_record(tmp_path: Path) -> None:
    once = _revised(tmp_path, (_co2_correction(),))
    twice = _revise(once, tmp_path / "again.zip", revision=2)

    first, second = _members(once), _members(twice)
    assert set(first) == set(second)
    assert {name: content for name, content in first.items() if name != MANIFEST} == {
        name: content for name, content in second.items() if name != MANIFEST
    }


def test_read_corrections(tmp_path: Path) -> None:
    listed = tmp_path / "corrections-1.0.csv"
    listed.write_text(
        COLUMNS
        + f"Flow,{FLOW_IDS['co2']},category,{AIR},{CORRECTED},filed under a path no rule places\n",
        encoding="utf-8",
    )

    assert read_corrections(listed) == (_co2_correction(),)

    header = tmp_path / "header.csv"
    header.write_text("entity,id,field,published,corrected\nFlow,1,name,a,b\n", encoding="utf-8")
    with pytest.raises(Invalid) as malformed:
        read_corrections(header)
    assert str(header) in str(malformed.value)

    entity = tmp_path / "entity.csv"
    entity.write_text(
        COLUMNS + f"Floww,{FLOW_IDS['co2']},category,{AIR},{CORRECTED},a typo\n",
        encoding="utf-8",
    )
    with pytest.raises(Invalid) as unknown:
        read_corrections(entity)
    assert "Floww" in str(unknown.value)
