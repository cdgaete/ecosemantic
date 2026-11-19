from __future__ import annotations

import pytest

from ecosemantic.package.canonical import (
    Placement,
    canonical_flow_record,
    cas_number,
    category_path,
    method_parts,
    place,
)
from ecosemantic.ports.types import CompartmentName

PLACED: list[tuple[str, CompartmentName, str | None]] = [
    ("air/urban air close to ground", "air", "urban air close to ground"),
    ("Resource/in ground", "natural resource", "in ground"),
    ("natural resource/in ground", "natural resource", "in ground"),
    ("water/ground-, long-term", "water", "ground-, long-term"),
    ("economic/primary production factor", "economic", "primary production factor"),
    ("inventory indicator/waste", "inventory indicator", "waste"),
    ("Emission to air/high population density", "air", "high population density"),
    ("Emissions to air/unspecified", "air", "unspecified"),
    ("Emission to soil/agricultural", "soil", "agricultural"),
    ("Resources/in water", "natural resource", "in water"),
    ("Economic/unspecified", "economic", "unspecified"),
    ("Immaterial emission/unspecified", "immaterial", "unspecified"),
    ("emission/air", "air", None),
    ("emission/air/troposphere/rural", "air", "troposphere, rural"),
    ("emission/ground/human-dominated/agricultural", "soil", "human-dominated, agricultural"),
    ("emission/non-FEDEFL/water/fresh water body", "water", "non-FEDEFL, fresh water body"),
    ("emission/non-FEDEFL/economic", "economic", "non-FEDEFL"),
    ("resource/ground/subterranean", "natural resource", "ground, subterranean"),
    ("resource/non-FEDEFL", "natural resource", "non-FEDEFL"),
    ("Ecosystem Services", "natural resource", "Ecosystem Services"),
]


@pytest.mark.parametrize(("path", "compartment", "sub"), PLACED)
def test_every_publisher_path_found_is_placed(
    path: str, compartment: CompartmentName, sub: str | None
) -> None:
    assert place(f"Elementary flows/{path}") == Placement(
        compartment=compartment, sub_compartment=sub
    )


@pytest.mark.parametrize(
    "category",
    [
        "Elementary flows/emission/non-FEDEFL",
        "Elementary flows/Social issues/unspecified",
        "",
        None,
    ],
)
def test_a_path_no_rule_places_is_not_placed(category: str | None) -> None:
    assert place(category) is None


@pytest.mark.parametrize(("path", "compartment", "sub"), PLACED)
def test_placing_a_placed_path_changes_nothing(
    path: str, compartment: CompartmentName, sub: str | None
) -> None:
    placement = Placement(compartment=compartment, sub_compartment=sub)
    assert place(category_path(placement)) == placement


def test_a_placement_names_its_flow_type() -> None:
    assert Placement(compartment="air", sub_compartment=None).flow_type == "emission"
    assert Placement(compartment="immaterial", sub_compartment=None).flow_type == "emission"
    assert (
        Placement(compartment="natural resource", sub_compartment="in ground").flow_type
        == "natural resource"
    )
    assert Placement(compartment="economic", sub_compartment=None).flow_type == "economic"
    assert (
        Placement(compartment="inventory indicator", sub_compartment="waste").flow_type
        == "inventory indicator"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("007732-18-5", ("7732-18-5", None)),
        ("50-00-0 ", ("50-00-0", None)),
        ("n.a.", (None, "n.a.")),
        ("7732190", (None, "7732190")),
        ("2234562", (None, "2234562")),
        ("1349-85-3", (None, "1349-85-3")),
        ("129874-8-4", (None, "129874-8-4")),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_cas_numbers(text: str | None, expected: tuple[str | None, str | None]) -> None:
    assert cas_number(text) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("climate change > GWP100", ("climate change", "GWP100")),
        ("Aquatic ecotoxicity", ("Aquatic ecotoxicity", "Aquatic ecotoxicity")),
        ("a > b > c", ("a", "b > c")),
    ],
)
def test_method_parts(name: str, expected: tuple[str, str]) -> None:
    assert method_parts(name) == expected


def test_a_flow_record_is_written_canonical() -> None:
    record: dict[str, object] = {
        "@type": "Flow",
        "@id": "f",
        "flowType": "ELEMENTARY_FLOW",
        "name": "x",
        "category": "Elementary flows/emission/air/troposphere/rural",
        "cas": "007732-18-5",
    }
    canonical = canonical_flow_record(record)
    assert canonical == {
        **record,
        "category": "Elementary flows/air/troposphere, rural",
        "cas": "7732-18-5",
    }
    assert canonical_flow_record({**record, "cas": "n.a."})["cas"] == "n.a."
    assert (
        canonical_flow_record({**record, "category": "Elementary flows/Social issues/unspecified"})[
            "category"
        ]
        == "Elementary flows/Social issues/unspecified"
    )
    product = {**record, "flowType": "PRODUCT_FLOW"}
    assert canonical_flow_record(product) == product
    assert canonical_flow_record(canonical) == canonical
