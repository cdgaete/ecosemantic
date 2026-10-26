"""Read a release's EcoSpold2 datasets into base rows."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from ecosemantic.databases.ecoinvent.masterdata import text, unit_name
from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model.entities import Uncertainty, UncertaintyType
from ecosemantic.package.base_writer import BaseDataset, BaseExchange

NS = "{http://www.EcoInvent.org/EcoSpold02}"
_DISTRIBUTIONS = get_args(UncertaintyType)
_IGNORED = ("pedigreeMatrix", "comment")

ZeroSpread = Literal["refuse", "none"]


@dataclass(frozen=True)
class Findings:
    """What a read collected: units the core lacks, features it did not read, features it read
    as documentation, and a distribution whose spread is zero."""

    unknown_units: dict[str, list[str]]
    unread: dict[str, list[str]]
    documentation: dict[str, list[str]]
    degenerate_uncertainty: list[str]


def _append(mapping: dict[str, list[str]], feature: str, native: str) -> None:
    """Note a feature under the dataset showing it; the read collects each dataset once when
    it returns."""
    mapping.setdefault(feature, []).append(native)


def _listed(mapping: dict[str, list[str]]) -> dict[str, list[str]]:
    """Collected features as reports read them: each dataset once, in the order it was seen."""
    return {feature: list(dict.fromkeys(natives)) for feature, natives in mapping.items()}


def _required(element: ET.Element, tag: str) -> ET.Element:
    """A child element the data always carries; a file that lacks it stops the read."""
    found = element.find(f"{NS}{tag}")
    if found is None:
        raise Invalid(f"{element.tag.removeprefix(NS)} holds no {tag}")
    return found


def _unit(element: ET.Element, native: str, findings: Findings) -> str:
    """The core's name for an exchange's unit, or the symbol the core does not know."""
    symbol = text(element, "unitName")
    try:
        return unit_name(symbol)
    except NotSupported:
        _append(findings.unknown_units, symbol, native)
        return symbol


def _amount(element: ET.Element) -> float:
    """The amount the release writes on an exchange."""
    return float(element.attrib["amount"])


def _degenerate(element: ET.Element, native: str, findings: Findings) -> None:
    """A distribution the release writes with a spread of zero: read as none, and counted."""
    findings.degenerate_uncertainty.append(f"{native}: {text(element, 'name')}")
    return None


def _number(
    distribution: ET.Element, attribute: str, native: str, findings: Findings
) -> float | None:
    """A distribution attribute as a number; absent, non-numeric and NaN spread data is
    invalid and refused at every zero-spread decision."""
    raw = distribution.get(attribute)
    if raw is None:
        _append(findings.unread, "uncertainty invalid", native)
        return None
    try:
        value = float(raw)
    except ValueError:
        _append(findings.unread, "uncertainty invalid", native)
        return None
    if math.isnan(value):
        _append(findings.unread, "uncertainty invalid", native)
        return None
    return value


def _uncertainty(element: ET.Element, native: str, findings: Findings) -> Uncertainty | None:
    """The distribution an exchange declares, or None when it declares none the core reads."""
    block = element.find(f"{NS}uncertainty")
    if block is None:
        return None
    distribution = next(
        (child for child in block if child.tag.removeprefix(NS) not in _IGNORED), None
    )
    if distribution is None:
        return None
    kind = distribution.tag.removeprefix(NS)
    if kind == "undefined":
        return None
    if kind not in _DISTRIBUTIONS:
        _append(findings.unread, f"uncertainty {kind}", native)
        return None
    if kind in ("lognormal", "normal"):
        variance = _number(distribution, "varianceWithPedigreeUncertainty", native, findings)
        if variance is None:
            return None
        if variance < 0:
            _append(findings.unread, "uncertainty invalid", native)
            return None
        if variance == 0:
            return _degenerate(element, native, findings)
        scale = math.sqrt(variance)
        if kind == "lognormal":
            params: dict[str, float | bool] = {
                "loc": float(distribution.attrib["mu"]),
                "scale": scale,
            }
            if _amount(element) < 0:
                params["negative"] = True
            return Uncertainty(type="lognormal", params=params)
        return Uncertainty(
            type="normal", params={"loc": float(distribution.attrib["meanValue"]), "scale": scale}
        )
    minimum = _number(distribution, "minValue", native, findings)
    maximum = _number(distribution, "maxValue", native, findings)
    if minimum is None or maximum is None:
        return None
    if minimum > maximum:
        _append(findings.unread, "uncertainty invalid", native)
        return None
    if minimum == maximum:
        return _degenerate(element, native, findings)
    if kind == "uniform":
        return Uncertainty(type="uniform", params={"minimum": minimum, "maximum": maximum})
    loc = _number(distribution, "mostLikelyValue", native, findings)
    if loc is None:
        return None
    return Uncertainty(
        type="triangular", params={"loc": loc, "minimum": minimum, "maximum": maximum}
    )


def _features(child: ET.Element, native: str, findings: Findings) -> None:
    """Note the features an exchange or parameter carries and the converter does not evaluate:
    the relation and variable a computed amount is written from, a property and whether it is a
    calculated amount, and the production volume a reference product is scaled from."""
    for attribute in ("variableName", "mathematicalRelation", "productionVolumeAmount"):
        if child.get(attribute) is not None:
            _append(findings.documentation, attribute, native)
    for prop in child.findall(f"{NS}property"):
        _append(findings.documentation, "property", native)
        if prop.get("isCalculatedAmount") is not None:
            _append(findings.documentation, "isCalculatedAmount", native)
        if prop.get("mathematicalRelation") is not None:
            _append(findings.documentation, "mathematicalRelation", native)


def _elementary_group(element: ET.Element) -> str:
    """The group an elementary exchange declares, its input group first."""
    return text(element, "inputGroup") or text(element, "outputGroup")


def _exchange(
    child: ET.Element,
    native: str,
    reference: ET.Element,
    findings: Findings,
) -> BaseExchange | None:
    """One flowData child as a base exchange, or None when a build cannot read it."""
    tag = child.tag.removeprefix(NS)
    _features(child, native, findings)
    if tag == "parameter":
        _append(findings.documentation, "parameter", native)
        return None
    if tag == "intermediateExchange":
        if child is reference:
            return BaseExchange(
                kind="production",
                input=native,
                amount=_amount(child),
                uncertainty=_uncertainty(child, native, findings),
            )
        group = text(child, "outputGroup")
        if group == "0":
            return None
        if group:
            _append(findings.unread, f"outputGroup {group}", native)
            return None
        group = text(child, "inputGroup")
        if group != "5":
            _append(findings.unread, f"inputGroup {group}".strip(), native)
            return None
        link = child.get("activityLinkId")
        if link is None:
            _append(findings.unread, "unlinked input", native)
            return None
        _unit(child, native, findings)
        return BaseExchange(
            kind="technosphere",
            input=f"{link}_{child.attrib['intermediateExchangeId']}",
            amount=_amount(child),
            uncertainty=_uncertainty(child, native, findings),
        )
    if tag == "elementaryExchange":
        group = _elementary_group(child)
        if group != "4":
            _append(findings.unread, f"elementary group {group}".strip(), native)
            return None
        _unit(child, native, findings)
        return BaseExchange(
            kind="biosphere",
            input=child.attrib["elementaryExchangeId"],
            amount=_amount(child),
            uncertainty=_uncertainty(child, native, findings),
        )
    _append(findings.unread, f"flowData {tag}", native)
    return None


def _dataset(
    path: Path,
    urls: dict[str, str],
    findings: Findings,
) -> BaseDataset | None:
    """One EcoSpold2 file as a base dataset, or None when it names no reference product."""
    native = path.stem
    root = ET.parse(path).getroot()
    element = root.find(f"{NS}childActivityDataset")
    if element is None:
        element = root.find(f"{NS}activityDataset")
    if element is None:
        raise Invalid(f"{path.name} holds no childActivityDataset or activityDataset")
    flow_data = _required(element, "flowData")
    references = [
        exchange
        for exchange in flow_data.findall(f"{NS}intermediateExchange")
        if text(exchange, "outputGroup") == "0"
    ]
    if len(references) != 1:
        _append(findings.unread, f"reference products: {len(references)}", native)
    if not references:
        return None
    reference = references[0]
    description = _required(element, "activityDescription")
    activity = _required(description, "activity")
    geography = _required(description, "geography")
    special = activity.get("specialActivityType")
    if special is not None:
        _append(findings.documentation, f"specialActivityType {special}", native)
    exchanges = tuple(
        exchange
        for child in flow_data
        for exchange in [_exchange(child, native, reference, findings)]
        if exchange is not None
    )
    return BaseDataset(
        code=native,
        native=native,
        name=text(activity, "activityName"),
        reference_product=text(reference, "name"),
        unit=_unit(reference, native, findings),
        location=text(geography, "shortname"),
        comment=None,
        url=urls.get(native),
        exchanges=exchanges,
    )


def read_datasets(ecospold: Path, urls: dict[str, str]) -> tuple[tuple[BaseDataset, ...], Findings]:
    """Read a release's EcoSpold2 datasets as base rows, with what a build cannot read noted."""
    findings = Findings(unknown_units={}, unread={}, documentation={}, degenerate_uncertainty=[])
    datasets = tuple(
        dataset
        for path in sorted((ecospold / "datasets").glob("*.spold"))
        for dataset in [_dataset(path, urls, findings)]
        if dataset is not None
    )
    return datasets, Findings(
        unknown_units=_listed(findings.unknown_units),
        unread=_listed(findings.unread),
        documentation=_listed(findings.documentation),
        degenerate_uncertainty=findings.degenerate_uncertainty,
    )
