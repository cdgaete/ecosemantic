"""EcoSpold2 datasets are read as base rows, with what a build cannot read collected."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.datasets import _append, read_datasets
from ecosemantic.errors import Invalid
from tests.databases.spold_fixture import (
    AIR,
    CO2,
    ELEC,
    ELEC_PRODUCT,
    IRON,
    NS,
    STEEL,
    STEEL_PRODUCT,
    TREAT,
    TREAT_PRODUCT,
    build_release,
)


def _dataset_element(root: ET.Element) -> ET.Element:
    element = root.find(f"{{{NS}}}childActivityDataset")
    if element is None:
        element = root.find(f"{{{NS}}}activityDataset")
    assert element is not None
    return element


def _exchange(root: ET.Element, flow: str) -> ET.Element:
    for exchange in _dataset_element(root).iter(f"{{{NS}}}intermediateExchange"):
        if exchange.get("intermediateExchangeId") == flow:
            return exchange
    raise AssertionError(flow)


def _rewrite(tmp_path: Path, native: str, change: Callable[[ET.Element], None]) -> None:
    path = tmp_path / "ecospold" / "datasets" / f"{native}.spold"
    tree = ET.parse(path)
    change(tree.getroot())
    tree.write(path, encoding="utf-8")


def _replace_distribution(root: ET.Element, tag: str, **attributes: str) -> None:
    uncertainty = _exchange(root, ELEC_PRODUCT).find(f"{{{NS}}}uncertainty")
    assert uncertainty is not None
    for child in list(uncertainty):
        if child.tag != f"{{{NS}}}pedigreeMatrix":
            uncertainty.remove(child)
    ET.SubElement(uncertainty, f"{{{NS}}}{tag}", attributes)


def test_each_dataset_is_its_reference_product_with_linked_inputs(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert [d.code for d in datasets] == [STEEL, ELEC, TREAT, AIR]
    by_code = {d.code: d for d in datasets}
    steel = by_code[STEEL]
    assert steel.native == STEEL and steel.name == "steel production"
    assert steel.reference_product == "steel" and steel.comment is None and steel.url is None
    assert steel.location == "NA" and steel.unit == "kilogram"
    kinds = [(e.kind, e.input, e.amount) for e in steel.exchanges]
    assert ("production", STEEL, 1.0) in kinds
    assert ("technosphere", ELEC, 2.0) in kinds
    # waste is taken as a negative input, linked to its treatment
    assert ("technosphere", TREAT, -0.2) in kinds
    assert ("biosphere", CO2, 1.5) in kinds and ("biosphere", IRON, 0.5) in kinds
    assert by_code[TREAT].exchanges[0].amount == -1.0
    air = by_code[AIR]
    assert ("technosphere", AIR, 0.1) in [(e.kind, e.input, e.amount) for e in air.exchanges]
    assert findings.unread == {} and findings.degenerate_uncertainty == []


def test_lognormal_takes_mu_and_the_root_of_the_pedigree_variance(tmp_path: Path) -> None:
    datasets, _ = read_datasets(build_release(tmp_path).ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    elec = next(e for e in steel.exchanges if e.input == ELEC)
    assert elec.uncertainty is not None and elec.uncertainty.type == "lognormal"
    assert elec.uncertainty.params["loc"] == pytest.approx(math.log(2.0))
    assert elec.uncertainty.params["scale"] == pytest.approx(0.2)  # sqrt(0.04)


def test_a_lognormal_on_a_negative_amount_is_marked_negative(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def negate(root: ET.Element) -> None:
        exchange = _exchange(root, ELEC_PRODUCT)
        exchange.set("amount", "-2.0")

    _rewrite(tmp_path, STEEL, negate)
    datasets, findings = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    elec = next(e for e in steel.exchanges if e.input == ELEC)
    assert elec.amount == -2.0
    assert elec.uncertainty is not None and elec.uncertainty.params["negative"] is True
    assert findings.degenerate_uncertainty == []


def test_a_zero_spread_is_collected_as_degenerate(tmp_path: Path) -> None:
    release = build_release(tmp_path, lognormal_variance=0.0)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert len(findings.degenerate_uncertainty) == 1
    assert findings.degenerate_uncertainty[0].startswith(f"{STEEL}: electricity")
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


@pytest.mark.parametrize(
    ("tag", "attributes"),
    [
        ("uniform", {"minValue": "1.0", "maxValue": "1.0"}),
        ("triangular", {"minValue": "1.0", "mostLikelyValue": "1.0", "maxValue": "1.0"}),
    ],
)
def test_a_spread_of_zero_is_degenerate_for_every_distribution(
    tmp_path: Path, tag: str, attributes: dict[str, str]
) -> None:
    release = build_release(tmp_path)
    _rewrite(tmp_path, STEEL, lambda root: _replace_distribution(root, tag, **attributes))
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert len(findings.degenerate_uncertainty) == 1
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


def test_the_url_comes_from_the_overview_mapping(tmp_path: Path) -> None:
    urls = {STEEL: "https://ecoquery.ecoinvent.org/3.10/cutoff/dataset/7/documentation"}
    datasets, _ = read_datasets(build_release(tmp_path).ecospold, urls=urls)
    assert next(d for d in datasets if d.code == STEEL).url == urls[STEEL]


def test_a_normal_takes_its_mean_and_the_root_of_the_variance(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(
            root, "normal", meanValue="2.0", varianceWithPedigreeUncertainty="0.04"
        ),
    )
    datasets, findings = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    elec = next(e for e in steel.exchanges if e.input == ELEC)
    assert elec.uncertainty is not None and elec.uncertainty.type == "normal"
    assert elec.uncertainty.params == {"loc": 2.0, "scale": pytest.approx(0.2)}
    assert findings.unread == {}


def test_a_uniform_and_a_triangular_keep_their_bounds(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(root, "uniform", minValue="1.0", maxValue="4.0"),
    )
    datasets, _ = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    elec = next(e for e in steel.exchanges if e.input == ELEC)
    assert elec.uncertainty is not None
    assert elec.uncertainty.params == {"minimum": 1.0, "maximum": 4.0}
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(
            root, "triangular", minValue="1.0", mostLikelyValue="2.0", maxValue="4.0"
        ),
    )
    datasets, _ = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    elec = next(e for e in steel.exchanges if e.input == ELEC)
    assert elec.uncertainty is not None
    assert elec.uncertainty.params == {"loc": 2.0, "minimum": 1.0, "maximum": 4.0}


def test_an_undefined_uncertainty_reads_as_none(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(tmp_path, STEEL, lambda root: _replace_distribution(root, "undefined"))
    datasets, findings = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None
    assert findings.unread == {}


def test_an_unknown_distribution_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(tmp_path, STEEL, lambda root: _replace_distribution(root, "beta", a="1"))
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"uncertainty beta": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


@pytest.mark.parametrize(
    "variance",
    [None, "not a number", "nan", "-0.04"],
)
def test_invalid_spread_data_is_unread_and_never_degenerate(
    tmp_path: Path, variance: str | None
) -> None:
    release = build_release(tmp_path)
    attributes = {} if variance is None else {"varianceWithPedigreeUncertainty": variance}
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(root, "lognormal", mu="0.693", **attributes),
    )
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"uncertainty invalid": [STEEL]}
    assert findings.degenerate_uncertainty == []
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


def test_an_inverted_uniform_is_invalid_spread_data(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(root, "uniform", minValue="4.0", maxValue="1.0"),
    )
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"uncertainty invalid": [STEEL]}
    assert findings.degenerate_uncertainty == []
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


def test_a_triangular_without_its_mode_is_invalid_spread_data(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _replace_distribution(root, "triangular", minValue="1.0", maxValue="4.0"),
    )
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"uncertainty invalid": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


@pytest.mark.parametrize(
    "attributes",
    [{"maxValue": "4.0"}, {"minValue": "1.0"}],
)
def test_a_uniform_without_a_bound_is_invalid_spread_data(
    tmp_path: Path, attributes: dict[str, str]
) -> None:
    release = build_release(tmp_path)
    _rewrite(tmp_path, STEEL, lambda root: _replace_distribution(root, "uniform", **attributes))
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"uncertainty invalid": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None


def test_the_features_read_as_documentation_are_collected_with_their_dataset(
    tmp_path: Path,
) -> None:
    release = build_release(tmp_path)

    def document(root: ET.Element) -> None:
        reference = _exchange(root, STEEL_PRODUCT)
        reference.set("variableName", "RP_amount")
        reference.set("productionVolumeAmount", "1000.0")
        property = ET.SubElement(reference, f"{{{NS}}}property", {"isCalculatedAmount": "true"})
        ET.SubElement(property, f"{{{NS}}}name").text = "carbon allocation"
        related = ET.SubElement(reference, f"{{{NS}}}property", {"mathematicalRelation": "a*b"})
        ET.SubElement(related, f"{{{NS}}}name").text = "net calorific value"
        activity = _dataset_element(root).find(f"{{{NS}}}activityDescription/{{{NS}}}activity")
        assert activity is not None
        activity.set("specialActivityType", "1")

    _rewrite(tmp_path, STEEL, document)
    _, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {}
    assert findings.documentation == {
        "variableName": [STEEL],
        "productionVolumeAmount": [STEEL],
        "property": [STEEL],
        "isCalculatedAmount": [STEEL],
        "mathematicalRelation": [STEEL],
        "specialActivityType 1": [STEEL],
    }


def test_a_mathematical_relation_is_collected_on_an_exchange(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path,
        STEEL,
        lambda root: _exchange(root, ELEC_PRODUCT).set("mathematicalRelation", "a*b"),
    )
    _, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {}
    assert findings.documentation == {"mathematicalRelation": [STEEL]}


def test_an_intermediate_output_that_is_not_the_reference_product_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def by_product(root: ET.Element) -> None:
        exchange = _exchange(root, ELEC_PRODUCT)
        group = exchange.find(f"{{{NS}}}inputGroup")
        assert group is not None
        group.tag = f"{{{NS}}}outputGroup"
        group.text = "3"

    _rewrite(tmp_path, STEEL, by_product)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"outputGroup 3": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert all(e.input != ELEC for e in steel.exchanges)


def test_an_input_without_a_link_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _rewrite(
        tmp_path, STEEL, lambda root: _exchange(root, ELEC_PRODUCT).attrib.pop("activityLinkId")
    )
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"unlinked input": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert all(e.input != ELEC for e in steel.exchanges)


def test_an_elementary_exchange_outside_group_four_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def regroup(root: ET.Element) -> None:
        element = next(
            exchange
            for exchange in _dataset_element(root).iter(f"{{{NS}}}elementaryExchange")
            if exchange.get("elementaryExchangeId") == CO2
        )
        group = element.find(f"{{{NS}}}outputGroup")
        assert group is not None
        group.text = "2"

    _rewrite(tmp_path, STEEL, regroup)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"elementary group 2": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert all(e.input != CO2 for e in steel.exchanges)


def test_more_than_one_reference_product_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def second_reference(root: ET.Element) -> None:
        group = _exchange(root, ELEC_PRODUCT).find(f"{{{NS}}}inputGroup")
        assert group is not None
        group.tag = f"{{{NS}}}outputGroup"
        group.text = "0"

    _rewrite(tmp_path, STEEL, second_reference)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"reference products: 2": [STEEL]}
    assert any(d.code == STEEL for d in datasets)


def test_an_unknown_unit_is_collected_with_the_dataset_that_names_it(tmp_path: Path) -> None:
    release = build_release(tmp_path, steel_unit="furlong")
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unknown_units == {"furlong": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert steel.unit == "furlong"


def test_a_parent_activity_dataset_is_read_like_a_child(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def promote(root: ET.Element) -> None:
        element = root.find(f"{{{NS}}}childActivityDataset")
        assert element is not None
        element.tag = f"{{{NS}}}activityDataset"

    _rewrite(tmp_path, STEEL, promote)
    datasets, findings = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    assert steel.name == "steel production"
    assert [e.input for e in steel.exchanges][:1] == [STEEL]
    assert findings.unread == {}


def test_a_parameter_element_is_documentation_and_not_an_exchange(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def add_parameter(root: ET.Element) -> None:
        flow_data = _dataset_element(root).find(f"{{{NS}}}flowData")
        assert flow_data is not None
        ET.SubElement(flow_data, f"{{{NS}}}parameter", {"parameterId": "p", "amount": "1.0"})

    _rewrite(tmp_path, STEEL, add_parameter)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {}
    assert findings.documentation == {"parameter": [STEEL]}
    assert len(next(d for d in datasets if d.code == STEEL).exchanges) == 5


def test_a_feature_two_exchanges_show_is_recorded_once(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def unlink(root: ET.Element) -> None:
        for flow in (ELEC_PRODUCT, TREAT_PRODUCT):
            _exchange(root, flow).attrib.pop("activityLinkId")

    _rewrite(tmp_path, STEEL, unlink)
    _, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"unlinked input": [STEEL]}


def test_one_unknown_unit_is_recorded_once_per_dataset(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def furlong(root: ET.Element) -> None:
        for unit in _dataset_element(root).iter(f"{{{NS}}}unitName"):
            unit.text = "furlong"

    _rewrite(tmp_path, STEEL, furlong)
    _, findings = read_datasets(release.ecospold, urls={})
    assert findings.unknown_units == {"furlong": [STEEL]}


def test_an_uncertainty_without_a_distribution_reads_as_none(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def strip(root: ET.Element) -> None:
        uncertainty = _exchange(root, ELEC_PRODUCT).find(f"{{{NS}}}uncertainty")
        assert uncertainty is not None
        for child in list(uncertainty):
            if child.tag != f"{{{NS}}}pedigreeMatrix":
                uncertainty.remove(child)

    _rewrite(tmp_path, STEEL, strip)
    datasets, findings = read_datasets(release.ecospold, urls={})
    steel = next(d for d in datasets if d.code == STEEL)
    assert next(e for e in steel.exchanges if e.input == ELEC).uncertainty is None
    assert findings.unread == {}


def test_an_intermediate_input_group_other_than_five_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def regroup(root: ET.Element) -> None:
        group = _exchange(root, ELEC_PRODUCT).find(f"{{{NS}}}inputGroup")
        assert group is not None
        group.text = "1"

    _rewrite(tmp_path, STEEL, regroup)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"inputGroup 1": [STEEL]}
    steel = next(d for d in datasets if d.code == STEEL)
    assert all(e.input != ELEC for e in steel.exchanges)


def test_an_unknown_flow_data_element_is_unread(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def add_unknown(root: ET.Element) -> None:
        flow_data = _dataset_element(root).find(f"{{{NS}}}flowData")
        assert flow_data is not None
        ET.SubElement(flow_data, f"{{{NS}}}something")

    _rewrite(tmp_path, STEEL, add_unknown)
    _, findings = read_datasets(release.ecospold, urls={})
    assert findings.unread == {"flowData something": [STEEL]}


def test_a_dataset_without_a_reference_product_is_unread_and_not_a_row(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def drop_reference(root: ET.Element) -> None:
        exchange = _exchange(root, STEEL_PRODUCT)
        group = exchange.find(f"{{{NS}}}outputGroup")
        assert group is not None
        exchange.remove(group)

    _rewrite(tmp_path, STEEL, drop_reference)
    datasets, findings = read_datasets(release.ecospold, urls={})
    assert "reference products: 0" in findings.unread
    assert all(d.code != STEEL for d in datasets)


def test_a_file_without_a_dataset_element_stops_the_read(tmp_path: Path) -> None:
    datasets = tmp_path / "ecospold" / "datasets"
    datasets.mkdir(parents=True)
    ET.ElementTree(ET.Element(f"{{{NS}}}ecoSpold")).write(
        datasets / f"{STEEL}.spold", encoding="utf-8"
    )
    with pytest.raises(Invalid, match="holds no childActivityDataset"):
        read_datasets(tmp_path / "ecospold", urls={})


def test_collecting_a_feature_does_not_scan_the_list_it_grows() -> None:
    scans: list[str] = []

    class Scanned(list[str]):
        def __contains__(self, value: object) -> bool:
            scans.append(str(value))
            return super().__contains__(value)

    class Mapping(dict[str, list[str]]):
        def setdefault(self, key: str, default: list[str] | None = None) -> list[str]:
            return super().setdefault(key, Scanned())

    mapping = Mapping()
    for _ in range(50):
        _append(mapping, "property", STEEL)
    assert scans == []


def test_a_dataset_without_flow_data_stops_the_read(tmp_path: Path) -> None:
    release = build_release(tmp_path)

    def drop_flows(root: ET.Element) -> None:
        element = _dataset_element(root)
        flow_data = element.find(f"{{{NS}}}flowData")
        assert flow_data is not None
        element.remove(flow_data)

    _rewrite(tmp_path, STEEL, drop_flows)
    with pytest.raises(Invalid, match="flowData"):
        read_datasets(release.ecospold, urls={})
