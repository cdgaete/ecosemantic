from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecosemantic.errors import MethodNotFound
from ecosemantic.model.entities import Method, method_id, method_named, nearest_methods

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
            impact_method="",
            impact_category="",
            indicator="",
        )


def test_a_method_of_a_key_names_its_parts_and_blanks_the_missing() -> None:
    m = Method.of(("db", "IPCC", "climate change"), "kg CO2-Eq")
    assert m.spec == "db > IPCC > climate change" and m.id == method_id(m.spec)
    assert m.tuple == ("db", "IPCC", "climate change") and m.unit == "kg CO2-Eq"
    assert (m.impact_method, m.impact_category, m.indicator) == ("IPCC", "climate change", "")


def test_a_method_of_an_bundle_key_splits_its_category_from_its_indicator() -> None:
    # a bundle names a category "category > indicator" (package/base_writer.py)
    key = ("db", "EF v3.1", "climate change > global warming potential (GWP100)")
    m = Method.of(key, "kg CO2-Eq")
    assert m.tuple == key and m.spec == " > ".join(key) and m.id == method_id(m.spec)
    assert (m.impact_method, m.impact_category, m.indicator) == (
        "EF v3.1",
        "climate change",
        "global warming potential (GWP100)",
    )
    assert m.id == Method.of(("db", "EF v3.1", *key[2].split(" > ")), "kg CO2-Eq").id


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
