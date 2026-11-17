from __future__ import annotations

from collections.abc import Sequence

import pytest

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import Method
from ecosemantic.ports.classifications import (
    classification_tree,
    method_tree,
    ordered_schemes,
    scheme_kind,
    values_under,
)
from ecosemantic.ports.types import (
    ClassificationNode,
    ClassificationScheme,
    ClassificationValue,
)
from tests.memory_background import methods

ISIC = "ISIC rev.4 ecoinvent"
CATEGORY = "Category"
BY_PRODUCT = "By-product classification"

ISIC_REST_3510 = "3510:Electric power generation, transmission and distribution"
ISIC_REST_3520 = "3520:Manufacture of gas; distribution of gaseous fuels through mains"
ISIC_REST_3530 = "3530:Steam and air conditioning supply"
ISIC_REST_35 = "35:Electricity, gas, steam and air conditioning supply"


def _values(scheme: str, rests: Sequence[tuple[str, int]]) -> list[ClassificationValue]:
    """Stored values of one scheme, each with the processes that carry it."""
    return [
        ClassificationValue(value=f"{scheme}: {rest}", processes=processes)
        for rest, processes in rests
    ]


ISIC_VALUES = _values(
    ISIC,
    [
        (ISIC_REST_3510, 3860),
        (ISIC_REST_3520, 726),
        (ISIC_REST_3530, 697),
        (ISIC_REST_35, 19),
    ],
)
PATH_VALUES = _values(
    CATEGORY,
    [
        ("transport systems/road/Transformation", 4),
        ("transport systems/rail", 2),
    ],
)


def _find(nodes: Sequence[ClassificationNode], wanted: str) -> ClassificationNode:
    """The node with the id, searched depth first from the roots."""
    pending = list(nodes)
    while pending:
        node = pending.pop(0)
        if node.id == wanted:
            return node
        pending.extend(node.children)
    raise AssertionError(f"no node {wanted}")


def _chain(root: ClassificationNode) -> list[ClassificationNode]:
    """The nodes from the root down the single-child path."""
    chain = [root]
    while chain[-1].children:
        [only] = chain[-1].children
        chain.append(only)
    return chain


def test_a_code_parent_takes_its_name_from_the_value_with_its_code() -> None:
    [isic_root] = classification_tree(ISIC, ISIC_VALUES)
    assert isic_root.id == "35"
    assert isic_root.label == "35"
    assert isic_root.code == "35"
    assert isic_root.name == "Electricity, gas, steam and air conditioning supply"
    assert isic_root.value == f"{ISIC}: {ISIC_REST_35}"
    assert isic_root.own == 19
    assert isic_root.processes == 5302  # 3860 + 726 + 697 + 19
    assert [child.id for child in isic_root.children] == ["351", "352", "353"]


def test_a_code_parent_without_a_value_takes_the_published_name() -> None:
    [isic_root] = classification_tree(ISIC, ISIC_VALUES)
    parent = _find(isic_root.children, "351")
    assert parent.name == "Electric power generation, transmission and distribution"
    assert parent.label == "351"
    assert parent.code == "351"
    assert parent.value is None
    assert parent.own == 0
    assert parent.processes == 3860
    [leaf] = parent.children
    assert leaf.id == "3510"
    assert leaf.name == "Electric power generation, transmission and distribution"
    assert leaf.value == f"{ISIC}: {ISIC_REST_3510}"
    assert leaf.own == 3860
    assert leaf.children == []


def test_a_division_without_a_value_takes_the_published_name() -> None:
    cereals = _values(
        ISIC, [("0111:Growing of cereals (except rice), leguminous crops and oil seeds", 474)]
    )
    [root] = classification_tree(ISIC, cereals)
    assert root.id == "01"
    assert root.name == "Crop and animal production, hunting and related service activities"
    group = _find(root.children, "011")
    assert group.name == "Growing of non-perennial crops"


def test_a_name_the_data_gives_wins_over_the_published_name() -> None:
    [root] = classification_tree(ISIC, _values(ISIC, [("20:Bespoke chemicals", 3)]))
    assert root.id == "20"
    # the published structure names 20 Manufacture of chemicals and chemical products
    assert root.name == "Bespoke chemicals"


def test_a_code_the_published_structure_lacks_keeps_its_code() -> None:
    [root] = classification_tree(ISIC, _values(ISIC, [("0411:Fishing", 2)]))
    assert root.id == "04"
    assert root.label == "04"
    assert root.name is None
    assert root.processes == 2


def test_cpc_groups_at_one_two_three_and_four_digits() -> None:
    [cpc_root] = classification_tree("CPC", _values("CPC", [("17100: Electrical energy", 5)]))
    chain = _chain(cpc_root)
    assert [node.id for node in chain] == ["1", "17", "171", "1710", "17100"]
    assert [node.processes for node in chain] == [5, 5, 5, 5, 5]
    assert chain[-1].name == "Electrical energy"
    assert chain[-1].own == 5


def test_a_path_scheme_nests_by_segment() -> None:
    tree = classification_tree(CATEGORY, PATH_VALUES)
    assert [node.id for node in tree] == ["transport systems"]
    root = _find(tree, "transport systems")
    assert root.label == "transport systems"
    assert root.code is None
    assert root.name is None
    assert root.value is None
    assert root.own == 0
    assert root.processes == 6  # 4 + 2
    assert [child.id for child in root.children] == [
        "transport systems/rail",
        "transport systems/road",
    ]
    leaf = _find(tree, "transport systems/road/Transformation")
    assert leaf.label == "Transformation"
    assert leaf.value == f"{CATEGORY}: transport systems/road/Transformation"
    assert leaf.own == 4
    assert leaf.processes == 4
    assert leaf.children == []


def test_a_flat_scheme_is_one_level() -> None:
    [waste] = classification_tree(BY_PRODUCT, _values(BY_PRODUCT, [("Waste", 12)]))
    assert waste.id == "Waste"
    assert waste.label == "Waste"
    assert waste.code is None
    assert waste.name is None
    assert waste.value == f"{BY_PRODUCT}: Waste"
    assert waste.own == 12
    assert waste.processes == 12
    assert waste.children == []


def test_values_under_a_node() -> None:
    assert values_under(ISIC, ISIC_VALUES, node="35") == [
        f"{ISIC}: {ISIC_REST_35}",
        f"{ISIC}: {ISIC_REST_3510}",
        f"{ISIC}: {ISIC_REST_3520}",
        f"{ISIC}: {ISIC_REST_3530}",
    ]
    assert values_under(ISIC, ISIC_VALUES, node="351") == [f"{ISIC}: {ISIC_REST_3510}"]
    assert values_under(ISIC, ISIC_VALUES, node="3510") == [f"{ISIC}: {ISIC_REST_3510}"]
    beside = _values(
        CATEGORY,
        [
            ("transport systems/road/Transformation", 4),
            ("transport systems/roadside", 3),
        ],
    )
    assert values_under(CATEGORY, beside, node="transport systems/road") == [
        f"{CATEGORY}: transport systems/road/Transformation"
    ]


def test_an_unknown_node_is_not_found() -> None:
    with pytest.raises(NotFound) as raised:
        values_under(ISIC, ISIC_VALUES, node="99")
    assert "99" in str(raised.value)
    assert ISIC in str(raised.value)


def test_a_value_outside_its_scheme_is_refused() -> None:
    outside = [ClassificationValue(value="CPC: 17100: Electrical energy", processes=5)]
    with pytest.raises(Invalid) as raised:
        classification_tree(ISIC, outside)
    assert "CPC: 17100: Electrical energy" in str(raised.value)
    assert ISIC in str(raised.value)


def test_two_values_with_the_same_code_are_refused() -> None:
    shared = _values(ISIC, [("3510:First name", 2), ("3510:Second name", 3)])
    with pytest.raises(Invalid) as raised:
        classification_tree(ISIC, shared)
    assert "First name" in str(raised.value)
    assert "Second name" in str(raised.value)


def test_schemes_are_ordered_isic_cpc_hs_then_paths_then_flat() -> None:
    schemes = [
        ClassificationScheme(scheme="CPC", processes=26533, values=675),
        ClassificationScheme(scheme=BY_PRODUCT, processes=26533, values=3),
        ClassificationScheme(scheme=ISIC, processes=26250, values=182),
        ClassificationScheme(scheme="HS2017", processes=19588, values=993),
        ClassificationScheme(scheme="EcoSpold01Categories", processes=8456, values=120),
    ]
    kinds = {
        "CPC": "code",
        BY_PRODUCT: "flat",
        ISIC: "code",
        "HS2017": "code",
        "EcoSpold01Categories": "path",
    }
    ordered = ordered_schemes(schemes, kinds)
    assert [scheme.scheme for scheme in ordered] == [
        ISIC,
        "CPC",
        "HS2017",
        "EcoSpold01Categories",
        BY_PRODUCT,
    ]


def test_schemes_of_one_group_are_ordered_by_processes_then_name() -> None:
    schemes = [
        ClassificationScheme(scheme="HS2017", processes=10, values=1),
        ClassificationScheme(scheme="HS2013", processes=10, values=1),
        ClassificationScheme(scheme="HS2019", processes=20, values=1),
    ]
    kinds = {"HS2017": "code", "HS2013": "code", "HS2019": "code"}
    ordered = ordered_schemes(schemes, kinds)
    assert [scheme.scheme for scheme in ordered] == ["HS2019", "HS2013", "HS2017"]


def test_a_scheme_ordered_as_code_but_named_by_no_key_is_refused() -> None:
    schemes = [ClassificationScheme(scheme="NACE", processes=3, values=1)]
    with pytest.raises(Invalid) as raised:
        ordered_schemes(schemes, {"NACE": "code"})
    assert "NACE" in str(raised.value)


def test_a_code_scheme_whose_names_hold_a_slash_is_a_code_scheme() -> None:
    slashed = _values(
        ISIC,
        [
            ("0145:Raising of swine/pigs", 3),
            ("0111:Growing of cereals (except rice), leguminous crops and oil seeds", 474),
        ],
    )
    assert scheme_kind(ISIC, slashed) == "code"
    [root] = classification_tree(ISIC, slashed)
    assert root.id == "01"
    assert root.processes == 477  # 474 + 3
    assert [child.id for child in root.children] == ["011", "014"]
    [leaf] = _find(root.children, "014").children
    assert leaf.id == "0145"
    assert leaf.name == "Raising of swine/pigs"


def test_scheme_kinds() -> None:
    assert scheme_kind(ISIC, ISIC_VALUES) == "code"
    assert scheme_kind(CATEGORY, PATH_VALUES) == "path"
    assert scheme_kind(BY_PRODUCT, _values(BY_PRODUCT, [("Waste", 12)])) == "flat"
    assert scheme_kind("NACE", _values("NACE", [("3511:x", 3)])) == "flat"


def test_methods_fold_into_family_category_indicator() -> None:
    tree = method_tree(methods())
    assert [family.name for family in tree] == ["gwp", "water"]
    [gwp] = [family for family in tree if family.name == "gwp"]
    [category] = gwp.categories
    assert category.name == "climate change"
    [indicator] = category.indicators
    assert indicator.id == "m_bff077f3bd"
    assert indicator.indicator == "GWP100"


def test_the_indicators_of_a_category_are_ordered_by_name() -> None:
    given = [
        Method.of(("fixture", "gwp", "climate change", "GWP20"), "kg CO2-Eq"),
        Method.of(("fixture", "gwp", "climate change", "GWP100"), "kg CO2-Eq"),
    ]
    [gwp] = method_tree(given)
    [category] = gwp.categories
    names = [indicator.indicator for indicator in category.indicators]
    assert names == ["GWP100", "GWP20"]  # names compare as strings, so 100 comes before 20
