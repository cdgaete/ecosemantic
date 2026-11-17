from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import method_id
from ecosemantic.view.app import build_view
from tests.fixture_data import FIXTURE_DB, GWP

ISIC = "ISIC rev.4 ecoinvent"
ISIC_PATH = "ISIC%20rev.4%20ecoinvent"
ECO = "EcoSpold01Categories"
GWP_ID = method_id(" > ".join(GWP))
NOWHERE = Path("/nonexistent-static")


@pytest.fixture(scope="module")
def client(context: ServerContext, full_server: FastMCP) -> Iterator[TestClient]:
    with TestClient(build_view(context, full_server, static=NOWHERE)) as client:
        yield client


def names(page: dict[str, Any]) -> list[str]:
    """The names of the hits one page of a listing carries, in the order it carries them."""
    return [str(hit["name"]) for hit in page["items"]]


def test_summary(client: TestClient) -> None:
    answered = client.get(f"/api/databases/{FIXTURE_DB}/summary")
    assert answered.status_code == 200
    assert answered.json()["value"] == {
        "processes": 12,
        "elementary_flows": 4,
        "indicators": 2,
        "units": 3,
        "locations": 1,
    }


def test_schemes_in_order(client: TestClient) -> None:
    listed = client.get(f"/api/databases/{FIXTURE_DB}/classifications").json()["value"]
    assert [(scheme["scheme"], scheme["processes"], scheme["values"]) for scheme in listed] == [
        (ISIC, 4, 4),
        ("CPC", 2, 2),
        (ECO, 4, 3),
        ("By-product classification", 2, 1),
    ]


def test_isic_tree(client: TestClient) -> None:
    answered = client.get(f"/api/databases/{FIXTURE_DB}/classifications/{ISIC_PATH}")
    assert answered.status_code == 200
    tree = answered.json()["value"]
    assert [node["id"] for node in tree] == ["24", "35"]
    metals, electricity = tree
    assert metals["name"] == "Manufacture of basic metals"
    assert metals["processes"] == 3
    assert metals["own"] == 1
    assert [child["id"] for child in metals["children"]] == ["241", "242"]
    assert electricity["name"] == "Electricity, gas, steam and air conditioning supply"
    assert electricity["processes"] == 1


def test_processes_under_a_node(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/classifications/{ISIC_PATH}/processes"
    listed = client.get(base, params={"node": "24"}).json()["value"]
    assert names(listed) == ["aluminium production", "copper production", "steel production"]
    narrowed = client.get(base, params={"node": "24", "query": "steel"}).json()["value"]
    assert names(narrowed) == ["steel production"]
    paged = client.get(base, params={"node": "24", "limit": 2}).json()["value"]
    assert names(paged) == ["aluminium production", "copper production"]
    rest = client.get(
        base, params={"node": "24", "limit": 2, "cursor": paged["next_cursor"]}
    ).json()["value"]
    assert names(rest) == ["steel production"]


def test_processes_under_a_path_node(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/classifications/{ECO}/processes"
    production = client.get(base, params={"node": "metals/production"}).json()["value"]
    assert names(production) == ["aluminium production", "steel production"]
    metals = client.get(base, params={"node": "metals"}).json()["value"]
    assert names(metals) == ["aluminium production", "copper production", "steel production"]


def test_an_unknown_node_is_404(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/classifications"
    unknown = client.get(f"{base}/{ISIC_PATH}/processes", params={"node": "99"})
    assert unknown.status_code == 404
    assert "99" in unknown.json()["message"]
    scheme = client.get(f"{base}/NACE")
    assert scheme.status_code == 404
    assert "NACE" in scheme.json()["message"]
    missing = client.get(f"{base}/{ISIC_PATH}/processes")
    assert missing.status_code == 400
    assert "node" in missing.json()["message"]


def test_an_unserved_database_is_404(client: TestClient) -> None:
    for resource in ("summary", "classifications"):
        answered = client.get(f"/api/databases/nope/{resource}")
        assert answered.status_code == 404
        assert "nope" in answered.json()["message"]


def test_compartments(client: TestClient) -> None:
    answered = client.get(f"/api/databases/{FIXTURE_DB}/compartments")
    assert answered.status_code == 200
    listed = answered.json()["value"]
    assert [(compartment["name"], compartment["flow_count"]) for compartment in listed] == [
        ("Resource", 1),
        ("air", 3),
    ]
    assert [(sub["name"], sub["flow_count"]) for sub in listed[1]["sub_compartments"]] == [
        ("urban air close to ground", 1)
    ]


def test_flows_in_a_sub_compartment(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/compartments"
    urban = client.get(
        f"{base}/air/flows", params={"sub_compartment": "urban air close to ground"}
    ).json()["value"]
    assert names(urban) == ["Particulate matter"]
    air = client.get(f"{base}/air/flows").json()["value"]
    assert names(air) == ["Carbon dioxide, fossil", "Methane, fossil", "Particulate matter"]
    for compartment, sub in (("soil", None), ("air", "stratosphere")):
        refused = client.get(f"{base}/{compartment}/flows", params={"sub_compartment": sub})
        assert refused.status_code == 404
        assert (sub or compartment) in refused.json()["message"]


def test_method_tree(client: TestClient) -> None:
    answered = client.get(f"/api/databases/{FIXTURE_DB}/impact-methods")
    assert answered.status_code == 200
    families = answered.json()["value"]
    assert [family["name"] for family in families] == ["gwp", "water"]
    gwp = families[0]
    assert [category["name"] for category in gwp["categories"]] == ["climate change"]
    indicators = gwp["categories"][0]["indicators"]
    assert [indicator["id"] for indicator in indicators] == [GWP_ID]


def test_factors(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/impact-methods"
    page = client.get(f"{base}/{GWP_ID}/factors").json()["value"]
    assert [(factor["name"], factor["factor"]) for factor in page["items"]] == [
        ("Carbon dioxide, fossil", 1.0),
        ("Methane, fossil", 28.0),
    ]
    narrowed = client.get(f"{base}/{GWP_ID}/factors", params={"query": "methane"}).json()["value"]
    assert names(narrowed) == ["Methane, fossil"]
    size = client.get(f"{base}/{GWP_ID}/factors", params={"limit": "abc"})
    assert size.status_code == 400
    assert "limit" in size.json()["message"]
    unknown = client.get(f"{base}/m_0000000000/factors")
    assert unknown.status_code == 404
    assert "m_0000000000" in unknown.json()["message"]
