"""The bundle comparison: two fixture bundles, one of them changed in a known way."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.profile import default_profile
from tests.databases.spold_fixture import CO2, ELEC_PRODUCT, build_release

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ecoinvent" / "compare_bundles.py"
_SPEC = importlib.util.spec_from_file_location("compare_bundles", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
compare = importlib.util.module_from_spec(_SPEC)
sys.modules["compare_bundles"] = compare
_SPEC.loader.exec_module(compare)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _built(root: Path, **overrides: object) -> Path:
    release = build_release(root / "release", **overrides)
    return build(release, default_profile(release), root / "out", NOW).bundle


def _change(entity: dict[str, object]) -> dict[str, object]:
    """The one change each kind of entity takes: the steel dataset's reference unit and one
    electricity amount, carbon dioxide's category, and its climate-change factor."""
    kind = entity.get("@type")
    if kind == "Process" and entity.get("name") == "steel production":
        for exchange in entity["exchanges"]:
            if exchange.get("isQuantitativeReference"):
                exchange["unit"]["name"] = "t"
            if exchange["flow"]["@id"] == ELEC_PRODUCT and exchange.get("isInput"):
                exchange["amount"] = 2.5
    elif kind == "Flow" and entity.get("@id") == CO2:
        entity["category"] = "Elementary flows/water/ocean"
    elif kind == "ImpactCategory":
        for factor in entity["impactFactors"]:
            if factor["flow"]["@id"] == CO2:
                factor["value"] = 1.5
    return entity


def _changed(source: Path, destination: Path) -> Path:
    """The source bundle with one changed amount, unit, category and factor."""
    with zipfile.ZipFile(source) as reader:
        documents = {info.filename: reader.read(info.filename) for info in reader.infolist()}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as writer:
        for name, document in documents.items():
            if name.endswith(".json"):
                document = json.dumps(_change(json.loads(document))).encode("utf-8")
            writer.writestr(name, document)
    return destination


def test_two_identical_bundles_differ_nowhere(tmp_path: Path) -> None:
    first = _built(tmp_path / "first")
    second = tmp_path / "copy.zip"
    shutil.copyfile(first, second)
    comparison, _ = compare.compare(first, second)
    assert comparison.report.counts == {}
    assert comparison.report.observed["datasets compared"] == 4
    assert comparison.report.observed["flows compared"] == 3
    assert comparison.report.observed["exchanges compared"] == 14
    assert comparison.report.observed["categories compared"] == 1
    assert comparison.report.observed["scores compared"] == 4


def test_a_changed_amount_unit_category_and_factor_are_each_named(tmp_path: Path) -> None:
    first = _built(tmp_path / "first")
    second = _changed(first, tmp_path / "second.zip")
    comparison, _ = compare.compare(first, second)
    counts = comparison.report.counts
    assert counts["exchange amount differs"] == 1
    assert counts["exchange unit differs"] == 1
    assert counts["dataset unit differs"] == 1
    assert counts["flow category differs"] == 1
    assert counts["CF differs"] == 1
    assert counts["score differs"] == 4
    assert len(comparison.report.examples["score differs"]) == 3
    assert comparison.report.largest["exchange amount differs"] > 0.0
    assert comparison.report.largest["CF differs"] > 0.0


def test_a_dataset_only_on_one_side_is_named_by_its_side(tmp_path: Path) -> None:
    first = _built(tmp_path / "first")
    second = _built(tmp_path / "second", steel_geography="RER")
    comparison, _ = compare.compare(first, second)
    assert comparison.report.counts["dataset only in left"] == 1
    assert comparison.report.counts["dataset only in right"] == 1
    assert "'RER'" in comparison.report.examples["dataset only in right"][0]


def test_the_command_answers_one_when_the_bundles_differ(tmp_path: Path) -> None:
    first = _built(tmp_path / "first")
    second = _changed(first, tmp_path / "second.zip")
    assert compare.main([str(first), str(second)]) == 1
    assert compare.main([str(first), str(first)]) == 0


def test_the_command_writes_both_dumps_under_the_work_directory(tmp_path: Path) -> None:
    first = _built(tmp_path / "first")
    work = tmp_path / "work"
    assert compare.main([str(first), str(first), "--work", str(work)]) == 0
    assert (work / "left" / "meta.json").is_file()
    assert (work / "right" / "B.npz").is_file()
