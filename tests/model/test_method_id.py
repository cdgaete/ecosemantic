from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecosemantic.errors import MethodNotFound
from ecosemantic.model.entities import (
    Method,
    method_id,
    method_named,
    nearest_methods,
    nearest_names,
)

SPEC = (
    "ecoinvent-3.11 > IPCC 2021 > climate change: total (excl. biogenic CO2)"
    " > global warming potential (GWP100)"
)


def test_method_id_is_deterministic_and_short() -> None:
    assert method_id(SPEC) == method_id(SPEC)
    assert method_id(SPEC).startswith("m_") and len(method_id(SPEC)) == 12
    assert method_id(SPEC) != method_id(SPEC.replace("3.11", "3.12"))


def test_method_carries_its_id() -> None:
    m = Method(
        id=method_id(SPEC),
        tuple=(
            "ecoinvent-3.11",
            "IPCC 2021",
            "climate change: total (excl. biogenic CO2)",
            "global warming potential (GWP100)",
        ),
        spec=SPEC,
        unit="kg CO2-Eq",
        impact_method="IPCC 2021",
        impact_category="climate change: total (excl. biogenic CO2)",
        indicator="global warming potential (GWP100)",
    )
    assert m.id == method_id(SPEC)
    with pytest.raises(ValidationError):
        Method(
            id="wrong",
            tuple=m.tuple,
            spec=SPEC,
            unit="x",
            impact_method=m.impact_method,
            impact_category=m.impact_category,
            indicator=m.indicator,
        )


def _method(impact_method: str, impact_category: str, indicator: str) -> Method:
    key = ("db", impact_method, impact_category, indicator)
    return Method(
        id=method_id(" > ".join(key)),
        tuple=key,
        spec=" > ".join(key),
        unit="kg CO2-Eq",
        impact_method=impact_method,
        impact_category=impact_category,
        indicator=indicator,
    )


def test_a_method_names_its_family_category_and_indicator() -> None:
    m = Method.of(("db", "IPCC", "AR6-100", "AR6-100"), "kg")
    assert (m.impact_method, m.impact_category, m.indicator) == ("IPCC", "AR6-100", "AR6-100")
    assert m.spec == "db > IPCC > AR6-100 > AR6-100" and m.id == method_id(m.spec)
    assert m.tuple == ("db", "IPCC", "AR6-100", "AR6-100") and m.unit == "kg"


def test_an_ecoinvent_method_keeps_its_id() -> None:
    m = Method.of(("ei", "CML", "climate change", "GWP100"), "kg")
    assert m.id == method_id("ei > CML > climate change > GWP100")
    assert (m.impact_method, m.impact_category, m.indicator) == (
        "CML",
        "climate change",
        "GWP100",
    )


@pytest.mark.parametrize(
    "key",
    [
        ("db", "IPCC", "climate change"),
        ("db", "IPCC", "climate change", "GWP100", "extra"),
    ],
)
def test_a_key_of_other_than_four_parts_is_refused(key: tuple[str, ...]) -> None:
    with pytest.raises(ValueError) as caught:
        Method.of(key, "kg")
    assert repr(key) in str(caught.value)


@pytest.mark.parametrize(
    "key",
    [("db", "", "c", "i"), ("db", "m", "", "i"), ("db", "m", "c", "")],
)
def test_a_blank_part_is_refused(key: tuple[str, str, str, str]) -> None:
    with pytest.raises(ValueError) as caught:
        Method.of(key, "kg")
    assert repr(key) in str(caught.value)


def test_a_method_with_a_blank_part_is_refused() -> None:
    for impact_method, impact_category, indicator in (
        ("", "c", "i"),
        ("m", "", "i"),
        ("m", "c", ""),
    ):
        with pytest.raises(ValidationError):
            _method(impact_method, impact_category, indicator)


def test_the_nearest_methods_ignore_case_and_punctuation() -> None:
    gwp = Method.of(("db", "gwp", "climate change", "GWP100"), "kg CO2-Eq")
    water = Method.of(("db", "water", "water use", "m3"), "m3")
    reference = "db > GWP > Climate Change > GWP 100"
    assert nearest_methods([water, gwp], reference) == [gwp, water]
    assert nearest_methods([water, gwp], reference, limit=1) == [gwp]


def test_a_method_is_named_by_its_id_or_its_specification_and_a_miss_carries_the_nearest() -> None:
    gwp = Method.of(("db", "gwp", "climate change", "GWP100"), "kg CO2-Eq")
    water = Method.of(("db", "water", "water use", "m3"), "m3")
    assert method_named([water, gwp], "db", gwp.id) == gwp
    assert method_named([water, gwp], "db", water.spec) == water
    with pytest.raises(MethodNotFound) as caught:
        method_named([water, gwp], "db", "db > GWP > climate change")
    assert caught.value.suggestions[0] == gwp


def test_an_id_no_method_carries_suggests_no_method_and_names_the_search() -> None:
    gwp = Method.of(("db", "gwp", "climate change", "GWP100"), "kg CO2-Eq")
    with pytest.raises(MethodNotFound) as caught:
        method_named([gwp], "db", "m_0123456789")
    assert caught.value.suggestions == []
    assert str(caught.value) == (
        "no method 'm_0123456789' in 'db'; search_methods answers the ids of its methods"
    )


def test_the_nearest_names_are_the_ones_that_read_alike_and_none_when_none_does() -> None:
    families = ["AWARE", "IPCC 2021", "IPCC 2021 (ISO 14067)", "ReCiPe 2016 Midpoint (H)"]
    assert nearest_names(families, "ipcc 2021") == ["IPCC 2021", "IPCC 2021 (ISO 14067)"]
    assert nearest_names(families, "recipe midpoint") == ["ReCiPe 2016 Midpoint (H)"]
    assert nearest_names(families, "zzz") == []
