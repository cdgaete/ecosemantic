from __future__ import annotations

import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.package.manifest import (
    MANIFEST,
    SCHEMA_VERSION,
    BaseDatabase,
    DatasetEntry,
    Manifest,
    changelog,
    read_manifest,
    write_manifest,
)

SYSTEM = uuid.UUID("0f0e0d0c-0b0a-4908-8706-050403020100")


def _manifest(pins: dict[str, str], base_version: str = "1") -> Manifest:
    return Manifest(
        mode="release",
        name="db",
        version="2",
        schema_version=SCHEMA_VERSION,
        built_at=datetime(2030, 1, 1, tzinfo=UTC),
        base=BaseDatabase(name="base", version=base_version),
        systems=[],
        datasets=[
            DatasetEntry(id=i, product_system_id=SYSTEM, process_code="p", case="c", pin=pin)
            for i, pin in pins.items()
        ],
    )


def test_the_manifest_is_written_last_and_reads_back(tmp_path: Path) -> None:
    bundle = tmp_path / "db.zip"
    with zipfile.ZipFile(bundle, "w") as zipped:
        zipped.writestr("olca-schema.json", '{"version": 2}')
    write_manifest(bundle, _manifest({"a": "1"}))
    with zipfile.ZipFile(bundle) as zipped:
        assert zipped.namelist()[-1] == MANIFEST
    assert read_manifest(bundle) == _manifest({"a": "1"})


def test_a_second_manifest_is_refused(tmp_path: Path) -> None:
    bundle = tmp_path / "db.zip"
    zipfile.ZipFile(bundle, "w").close()
    write_manifest(bundle, _manifest({}))
    with pytest.raises(Invalid, match="already carries"):
        write_manifest(bundle, _manifest({}))


@pytest.mark.parametrize(
    ("content", "named"),
    [
        (None, "carries no"),
        ('{"mode": "draft"}', "mode"),
        (
            _manifest({}).model_copy(update={"schema_version": 9}).model_dump_json(),
            "schema_version 9",
        ),
    ],
)
def test_a_missing_or_unknown_manifest_is_invalid(
    tmp_path: Path, content: str | None, named: str
) -> None:
    bundle = tmp_path / "db.zip"
    with zipfile.ZipFile(bundle, "w") as zipped:
        if content is not None:
            zipped.writestr(MANIFEST, content)
    with pytest.raises(Invalid, match=named):
        read_manifest(bundle)


def test_the_changelog_sorts_by_id_and_pin() -> None:
    before = _manifest({"kept": "1", "moved": "1", "gone": "1"})
    after = _manifest({"kept": "1", "moved": "2", "new": "1"})
    log = changelog(before, after)
    assert (log.added, log.removed, log.changed, log.unchanged) == (
        ["new"],
        ["gone"],
        ["moved"],
        ["kept"],
    )
    assert log.previous == "2" and not log.base_changed
    assert changelog(before, _manifest({}, base_version="2")).base_changed
    assert changelog(None, after).added == ["kept", "moved", "new"]
