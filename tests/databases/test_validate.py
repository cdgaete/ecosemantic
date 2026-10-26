from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from python_calamine import CalamineWorkbook
from scipy.sparse import csr_matrix

from ecosemantic.databases.ecoinvent import validate as validate_module
from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.profile import default_profile
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.databases.ecoinvent.validate import _Comparison, _Export, validate
from ecosemantic.errors import Invalid
from tests.databases.spold_fixture import (
    CATEGORY,
    ELEC,
    ELEC_ACTIVITY,
    INDICATOR,
    IRON,
    KILOGRAM,
    METHOD,
    NS,
    STEEL,
    UNUSED,
    UNUSED_FACTOR,
    _write_workbook,
    build_release,
    offset_cumulative,
    tamper_cumulative,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WIDGET_ACTIVITY = "00000040-0000-4000-8000-000000000040"
WIDGET_PRODUCT = "00000041-0000-4000-8000-000000000041"
WIDGET = f"{WIDGET_ACTIVITY}_{WIDGET_PRODUCT}"
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _built(tmp_path: Path) -> tuple[Release, Path]:
    release = build_release(tmp_path)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    return release, written.bundle


def _rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle, delimiter=";"))


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)


def _corrupt_elec_iron(bundle: Path, destination: Path, factor: float) -> Path:
    """A copy of the bundle with electricity's own Iron input multiplied, a corruption the B
    tolerance admits while it flips the score its two cancelling contributions make."""
    with zipfile.ZipFile(bundle) as reader:
        documents = {item.filename: reader.read(item.filename) for item in reader.infolist()}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as writer:
        for name, document in documents.items():
            if name.startswith("processes/"):
                entity = json.loads(document)
                if entity.get("name") == "electricity production":
                    for exchange in entity["exchanges"]:
                        if exchange["flow"]["@id"] == IRON and exchange["isInput"]:
                            exchange["amount"] = exchange["amount"] * factor
                document = json.dumps(entity).encode()
            writer.writestr(name, document)
    return destination


def test_validation_of_the_fixture_matches_its_own_matrices(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.mismatches == []
    assert result.counts["scores"] == 4 * 1


def test_the_bundle_level_is_exact_on_the_fixture(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.mismatches == []
    assert result.counts["self_consumption_folded"] == 1
    assert all(result.largest_rel_diff[kind] <= 1e-6 for kind in ("A", "B", "C", "scores"))


def test_a_validation_reports_its_steps_and_the_background_it_saved(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert list(result.seconds) == [
        "read",
        "compile",
        "save",
        "load",
        "factorise",
        "intensities",
        "read_export",
        "compare",
    ]
    assert all(value >= 0.0 for value in result.seconds.values())
    saved = tmp_path / "compiled"
    assert (saved / "background.json").is_file()
    assert result.saved_bytes == sum(path.stat().st_size for path in saved.iterdir())


def test_validation_is_clean_with_an_installed_flow_no_exchange_uses(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.mismatches == []
    assert result.largest_rel_diff["C"] == 0.0
    assert result.counts["flows"] == 2


def test_a_factor_for_a_flow_the_export_lacks_is_not_compared(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert UNUSED_FACTOR != 0.0
    assert result.largest_rel_diff["C"] == 0.0
    assert not any("Argon" in m for m in result.mismatches)


def test_validation_names_a_flow_the_export_uses_but_no_exchange_does(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    index = release.matrix / "ee_index.csv"
    rows = _rows(index)
    rows.append(["Argon", "air", "unspecified", "kg", "2"])
    _write_rows(index, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("no exchange uses: Argon (air/unspecified)" in m for m in result.mismatches)


def test_a_clean_validation_reports_its_counts_and_its_largest_differences(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.counts == {
        "datasets": 4,
        "flows": 2,
        "categories": 1,
        "categories_without_reference": 0,
        "self_consumption_folded": 1,
        "scores": 4,
        "workbook_disagreeing_scores": 0,
    }
    assert result.unreferenced == []
    assert result.largest_rel_diff["units"] == 0.0
    assert all(result.largest_rel_diff[kind] <= 1e-6 for kind in ("A", "B", "C", "scores"))


def test_validation_names_a_score_that_differs(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    tamper_cumulative(release, STEEL, factor=1.01)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("steel" in m for m in result.mismatches)


def test_a_cancelling_score_is_a_mismatch(tmp_path: Path) -> None:
    release = build_release(tmp_path, cancelling_factor=True)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    # electricity's +0.5 CO2 and -0.5 Iron contributions cancel; its magnitude is 1.0, so 1e-13
    # is roundoff against it and a whole relative difference against a score of zero
    offset_cumulative(release, ELEC, 1e-13)
    result = validate(release, written.bundle, tmp_path / "compiled", tolerance=1e-6)
    assert "cancelling_scores" not in result.counts
    assert "scores_against_magnitude" not in result.largest_rel_diff
    assert any("electricity production" in m for m in result.mismatches)


def test_a_cancelling_score_through_a_sub_tolerance_matrix_corruption_fails(
    tmp_path: Path,
) -> None:
    release = build_release(tmp_path, cancelling_factor=True)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    # electricity's Iron input times 1.0000005: the bundle's B differs from the export's by 5e-7,
    # under the 1e-6 tolerance, while the score goes from 0 to 2.5e-7, which is roundoff against
    # the dataset's magnitude of 1.0 and a whole relative difference against a score of zero
    corrupted = _corrupt_elec_iron(written.bundle, tmp_path / "corrupt.zip", 1 + 5e-7)
    result = validate(release, corrupted, tmp_path / "compiled", tolerance=1e-6)
    assert 0.0 < result.largest_rel_diff["B"] < 1e-6
    assert any("electricity production" in m for m in result.mismatches)


def test_a_score_whose_difference_exceeds_its_magnitude_is_a_mismatch(tmp_path: Path) -> None:
    release = build_release(tmp_path, cancelling_factor=True)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    offset_cumulative(release, ELEC, 1.0)
    result = validate(release, written.bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("electricity production" in m for m in result.mismatches)


def test_a_tampered_workbook_category_the_profile_lists_passes_and_is_counted(
    tmp_path: Path,
) -> None:
    release, bundle = _built(tmp_path)
    tamper_cumulative(release, STEEL, factor=1.01)
    result = validate(
        release,
        bundle,
        tmp_path / "compiled",
        tolerance=1e-6,
        workbook_disagrees=[f"{METHOD} > {CATEGORY} > {INDICATOR}"],
        matrix_reference_tolerance=1e-5,
    )
    assert result.mismatches == []
    assert result.counts["workbook_disagreeing_scores"] == 1
    assert result.largest_rel_diff["workbook_disagrees"] > 1e-6


def test_a_tampered_workbook_category_the_profile_does_not_list_fails(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    tamper_cumulative(release, STEEL, factor=1.01)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.counts["workbook_disagreeing_scores"] == 0
    assert any("steel" in message for message in result.mismatches)


def test_a_workbook_category_the_profile_lists_but_that_agrees_fails(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    label = f"{METHOD} > {CATEGORY} > {INDICATOR}"
    result = validate(
        release,
        bundle,
        tmp_path / "compiled",
        tolerance=1e-6,
        workbook_disagrees=[label],
        matrix_reference_tolerance=1e-5,
    )
    assert any(label in message for message in result.mismatches)


def test_a_workbook_disagreeing_category_needs_a_matrix_reference_tolerance(
    tmp_path: Path,
) -> None:
    release, bundle = _built(tmp_path)
    label = f"{METHOD} > {CATEGORY} > {INDICATOR}"
    with pytest.raises(Invalid):
        validate(release, bundle, tmp_path / "compiled", tolerance=1e-6, workbook_disagrees=[label])


def test_a_workbook_disagreeing_label_no_category_names_is_invalid(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    label = "Ecological Scarcity 2021 > nowhere > nothing"
    with pytest.raises(Invalid) as raised:
        validate(
            release,
            bundle,
            tmp_path / "compiled",
            tolerance=1e-6,
            workbook_disagrees=[label],
            matrix_reference_tolerance=1e-5,
        )
    assert label in str(raised.value)


def _matrix_reference_report(
    matrix_score: float, matrix_tolerance: float
) -> validate_module._Report:
    """A comparison of one dataset under one category: the bundle scores 1 and the matrix export
    scores ``matrix_score``."""
    report = validate_module._Report(1e-6)
    comparison = _Comparison(
        "ecoinvent-test",
        None,
        _Export(
            activities=[("dataset", "GLO", "product", "kg")],
            flows=[("flow", "air", "unspecified", "kg")],
            lcia=[("M", "C", "I", "kg")],
            A=csr_matrix([[1.0]]),
            B=csr_matrix([[1.0]]),
            C=csr_matrix([[1.0]]),
            cumulative_triples=[("M", "C", "I")],
            cumulative={("dataset", "GLO", "product"): np.array([1.0])},
        ),
        report,
        {"M > C > I": (np.array([matrix_score]), matrix_tolerance)},
    )
    comparison.activity_keep = [0]
    comparison.lcia_keep = [0]
    comparison.lcia_positions = {("M", "C", "I"): 0}
    # the bundle's one score, read where the engine's intensities are
    comparison._scores = lambda: np.array([[1.0]])
    comparison._compare_scores()
    return report


def test_a_matrix_reference_score_off_by_five_micro_passes_at_its_own_tolerance() -> None:
    report = _matrix_reference_report(1.000005, 1e-5)
    assert report.mismatches == []
    assert report.largest["scores_against_matrix_export"] == pytest.approx(5e-6, rel=1e-3)


def test_a_matrix_reference_score_off_by_five_micro_fails_at_the_command_tolerance() -> None:
    report = _matrix_reference_report(1.000005, 1e-6)
    assert any("dataset" in message for message in report.mismatches)


def test_validation_names_a_unit_that_differs(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    index = release.matrix / "ie_index.csv"
    rows = _rows(index)
    rows[1][3] = "kWh"
    _write_rows(index, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("the export says kilowatt hour" in m for m in result.mismatches)
    assert result.largest_rel_diff["units"] == 1.0


def test_validation_names_an_activity_the_export_does_not_hold(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    index = release.matrix / "ie_index.csv"
    rows = _rows(index)
    rows.append(["ghost production", "GLO", "ghost", "kg", "3"])
    _write_rows(index, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("names no installed dataset: ghost production" in m for m in result.mismatches)


def test_validation_names_a_flow_the_export_does_not_hold(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    index = release.matrix / "ee_index.csv"
    rows = _rows(index)
    rows.append(["Ghost", "air", "unspecified", "kg", "2"])
    _write_rows(index, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("names no installed flow: Ghost (air/unspecified)" in m for m in result.mismatches)


def test_validation_names_a_category_the_export_does_not_hold(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    index = release.matrix / "LCIA_index.csv"
    rows = _rows(index)
    rows[1] = ["Ghost", "x", "y", "kg", "0"]
    _write_rows(index, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("names no installed method: Ghost > x > y" in m for m in result.mismatches)
    assert result.counts["categories"] == 0
    assert result.counts["scores"] == 0


def test_validation_names_a_dataset_the_cumulative_lcia_does_not_hold(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    sheet = CalamineWorkbook.from_path(str(release.cumulative_lcia)).get_sheet_by_name("LCIA")
    rows = [row for row in sheet.to_python() if not str(row[0]).startswith(ELEC_ACTIVITY)]
    _write_workbook(release.cumulative_lcia, {"LCIA": rows})
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any("no row for electricity production" in m for m in result.mismatches)
    assert result.counts["scores"] == 3


def test_validation_names_a_matrix_entry_that_differs(tmp_path: Path) -> None:
    release, bundle = _built(tmp_path)
    path = release.matrix / "A_public.csv"
    rows = _rows(path)
    rows[2][2] = "-1.0"
    _write_rows(path, rows)
    result = validate(release, bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any(
        m.startswith("A[electricity production [GLO], steel production [NA]]")
        for m in result.mismatches
    )
    assert result.largest_rel_diff["A"] > 1e-6


def test_validation_lists_a_category_no_reference_names(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_category=True)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    result = validate(release, written.bundle, tmp_path / "compiled", tolerance=1e-6)
    assert result.mismatches == []
    assert result.unreferenced == ["IPCC 2021 > water use > WDP"]
    assert result.counts["categories_without_reference"] == 1
    assert result.counts["categories"] == 1


def _add_widget(release: Release) -> None:
    """A fifth dataset the fixture's matrix export does not list, with its overview URL."""
    root = ET.Element(f"{{{NS}}}ecoSpold")
    dataset = ET.SubElement(root, f"{{{NS}}}childActivityDataset")
    description = ET.SubElement(dataset, f"{{{NS}}}activityDescription")
    activity = ET.SubElement(description, f"{{{NS}}}activity", {"id": WIDGET_ACTIVITY})
    ET.SubElement(activity, f"{{{NS}}}activityName", {_LANG: "en"}).text = "widget production"
    geography = ET.SubElement(description, f"{{{NS}}}geography")
    ET.SubElement(geography, f"{{{NS}}}shortname", {_LANG: "en"}).text = "GLO"
    flow_data = ET.SubElement(dataset, f"{{{NS}}}flowData")
    exchange = ET.SubElement(
        flow_data,
        f"{{{NS}}}intermediateExchange",
        {
            "id": WIDGET,
            "unitId": KILOGRAM,
            "amount": "1.0",
            "intermediateExchangeId": WIDGET_PRODUCT,
        },
    )
    ET.SubElement(exchange, f"{{{NS}}}name", {_LANG: "en"}).text = "widget"
    ET.SubElement(exchange, f"{{{NS}}}unitName", {_LANG: "en"}).text = "kg"
    ET.SubElement(exchange, f"{{{NS}}}outputGroup").text = "0"
    ET.ElementTree(root).write(release.ecospold / "datasets" / f"{WIDGET}.spold", encoding="utf-8")
    sheet = CalamineWorkbook.from_path(str(release.overview)).get_sheet_by_name("Cut-Off AO")
    rows = sheet.to_python()
    rows.append(
        [WIDGET, WIDGET_ACTIVITY, "https://example.test/widget", "widget production", "GLO"]
    )
    _write_workbook(release.overview, {"Cut-Off AO": rows})


def _add_argon_exchange(release: Release) -> None:
    """A used elementary flow the fixture's ee_index does not list."""
    path = release.ecospold / "datasets" / f"{STEEL}.spold"
    tree = ET.parse(path)
    dataset = tree.getroot().find(f"{{{NS}}}childActivityDataset")
    assert dataset is not None
    flow_data = dataset.find(f"{{{NS}}}flowData")
    assert flow_data is not None
    exchange = ET.SubElement(
        flow_data,
        f"{{{NS}}}elementaryExchange",
        {"id": UNUSED, "unitId": KILOGRAM, "amount": "0.1", "elementaryExchangeId": UNUSED},
    )
    ET.SubElement(exchange, f"{{{NS}}}name", {_LANG: "en"}).text = "Argon"
    ET.SubElement(exchange, f"{{{NS}}}unitName", {_LANG: "en"}).text = "kg"
    ET.SubElement(exchange, f"{{{NS}}}inputGroup").text = "4"
    tree.write(path, encoding="utf-8")


def test_validation_names_an_installed_dataset_the_export_does_not_hold(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _add_widget(release)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    result = validate(release, written.bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any(
        "names no matrix export activity: widget production [GLO] widget" in m
        for m in result.mismatches
    )


def test_validation_names_an_installed_flow_the_export_does_not_hold(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _add_argon_exchange(release)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    result = validate(release, written.bundle, tmp_path / "compiled", tolerance=1e-6)
    assert any(
        "names no matrix export flow: Argon (air/unspecified)" in m for m in result.mismatches
    )
