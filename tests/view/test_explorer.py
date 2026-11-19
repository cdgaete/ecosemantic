from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from starlette.testclient import TestClient

from ecosemantic.installs.sources import install_source
from ecosemantic.local import build_context
from ecosemantic.mcp.context import AGENT, ServerContext
from ecosemantic.mcp.discovery import NO_DATABASE
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import method_id
from ecosemantic.ports.types import InstallDraft, InstallProgress
from ecosemantic.view.app import build_view
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DATABASE, FIXTURE_DB, FLOW_IDS, GWP
from tests.openlca_fixture import NAME as OLCA_NAME
from tests.openlca_fixture import PUBLISHER_FLOW_IDS, build_package

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


def test_the_databases_listing_counts_each_databases_processes(client: TestClient) -> None:
    listed = client.get("/api/databases").json()
    assert listed["hint"] is None
    assert [entry["name"] for entry in listed["value"]] == [FIXTURE_DB, "looped"]
    counted = next(entry for entry in listed["value"] if entry["name"] == FIXTURE_DB)
    assert counted == {**FIXTURE_DATABASE.model_dump(mode="json"), "processes": 12}


def test_an_engine_that_serves_no_database_is_led_to_its_sources(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    systems = tmp_path / "systems"
    systems.mkdir()
    empty = build_context(data, systems)
    try:
        with TestClient(build_view(empty, build_server(), static=NOWHERE)) as client:
            listed = client.get("/api/databases").json()
    finally:
        empty.close()
    assert listed["value"] == []
    assert listed["hint"] == NO_DATABASE


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


def test_a_filtered_listing_counts_what_its_filter_keeps(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/classifications/{ISIC_PATH}/processes"
    whole = client.get(base, params={"node": "24"}).json()["value"]
    assert whole["total"] == 3
    narrowed = client.get(base, params={"node": "24", "query": "steel"}).json()["value"]
    assert narrowed["total"] == 1


def test_a_listing_route_answers_the_page_that_holds_an_item(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/classifications/{ISIC_PATH}/processes"
    page = client.get(base, params={"node": "24", "limit": 2, "item": CODES["steel"]}).json()[
        "value"
    ]
    assert names(page) == ["steel production"]
    assert page["previous_cursor"] == "0"


def test_the_flows_listing_is_in_name_order_under_a_filter(client: TestClient) -> None:
    page = client.get(
        f"/api/databases/{FIXTURE_DB}/compartments/air/flows", params={"query": "fossil"}
    ).json()["value"]
    assert names(page) == ["Carbon dioxide, fossil", "Methane, fossil"]
    assert page["total"] == 2


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
        ("air", 3),
        ("natural resource", 1),
    ]
    assert [(sub["name"], sub["flow_count"]) for sub in listed[0]["sub_compartments"]] == [
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


def test_the_flows_of_a_process_are_read_in_one_request(client: TestClient) -> None:
    absent = FLOW_IDS["ch4"][:-1] + "0"
    ids = [FLOW_IDS["water_in"], absent, FLOW_IDS["co2"]]
    answered = client.post(f"/api/databases/{FIXTURE_DB}/elementary-flows/read", json={"ids": ids})
    assert answered.status_code == 200
    assert [flow["ref"]["id"] for flow in answered.json()["value"]] == [
        FLOW_IDS["water_in"],
        FLOW_IDS["co2"],
    ]
    by_flows_name = client.post(
        f"/api/databases/{FIXTURE_BIO}/elementary-flows/read", json={"ids": ids}
    )
    assert by_flows_name.status_code == 200
    assert [flow["name"] for flow in by_flows_name.json()["value"]] == [
        "Water, river",
        "Carbon dioxide, fossil",
    ]
    base = f"/api/databases/{FIXTURE_DB}/elementary-flows/read"
    stated = client.post(base, json={"ids": "x"})
    assert stated.status_code == 400
    assert stated.json()["error"] == "invalid"
    assert "ids" in stated.json()["message"]
    unknown = client.post("/api/databases/nope/elementary-flows/read", json={"ids": []})
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "not_found"


def test_method_tree(client: TestClient) -> None:
    answered = client.get(f"/api/databases/{FIXTURE_DB}/impact-methods")
    assert answered.status_code == 200
    families = answered.json()["value"]
    assert [family["name"] for family in families] == ["gwp", "water"]
    gwp = families[0]
    assert [category["name"] for category in gwp["categories"]] == ["climate change"]
    indicators = gwp["categories"][0]["indicators"]
    assert [indicator["id"] for indicator in indicators] == [GWP_ID]


def test_every_indicator_of_an_openlca_method_is_named(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    systems = tmp_path / "systems"
    systems.mkdir()
    draft = InstallDraft(
        source="openlca",
        actor=AGENT,
        version="1",
        system_model="unit process",
        package=str(build_package(tmp_path / "fixture.zip")),
        name=OLCA_NAME,
        drop_unlinked=True,
    )

    def quiet(_progress: InstallProgress) -> None:
        return None

    install_source(data, draft, None, quiet)
    built = build_context(data, systems)
    try:
        app = build_view(built, build_server(built), static=NOWHERE)
        with TestClient(app) as client:
            answered = client.get(f"/api/databases/{OLCA_NAME}/impact-methods")
    finally:
        built.close()
    assert answered.status_code == 200
    families = answered.json()["value"]
    assert [family["name"] for family in families] == ["fixture method"]
    for family in families:
        for category in family["categories"]:
            assert category["indicators"]
            for indicator in category["indicators"]:
                assert indicator["indicator"] == category["name"]


async def test_each_vocabulary_reads_canonical_through_the_tools_and_the_explorer(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    systems = tmp_path / "systems"
    systems.mkdir()
    draft = InstallDraft(
        source="openlca",
        actor=AGENT,
        version="1",
        system_model="unit process",
        package=str(build_package(tmp_path / "publishers.zip", publisher_flows=True)),
        name=OLCA_NAME,
        drop_unlinked=True,
    )

    def quiet(_progress: InstallProgress) -> None:
        return None

    install_source(data, draft, None, quiet)
    built = build_context(data, systems)
    try:
        server = build_server(built)
        async with Client(server) as client:
            hit = (
                await client.call_tool(
                    "search_elementary_flows",
                    {"database": OLCA_NAME, "query": "Nitrogen oxides"},
                )
            ).structured_content["items"][0]
            flows = {
                key: (
                    await client.call_tool(
                        "get_elementary_flow",
                        {"database": OLCA_NAME, "flow_id": PUBLISHER_FLOW_IDS[key]},
                    )
                ).structured_content["value"]
                for key in ("nox", "dust", "ore", "wages")
            }
        app = build_view(built, server, static=NOWHERE)
        with TestClient(app) as client:
            listed = client.get(f"/api/databases/{OLCA_NAME}/compartments").json()["value"]
            vocabulary = client.get(f"/api/databases/{OLCA_NAME}/vocabulary/locations").json()[
                "value"
            ]
    finally:
        built.close()
    assert [(term["value"], term["detail"]) for term in vocabulary] == [("GLO", "Global")]
    assert (hit["compartment"], hit["sub_compartment"], hit["flow_type"]) == (
        "air",
        "unspecified",
        "emission",
    )
    assert {
        key: (flow["compartment"], flow["sub_compartment"], flow["flow_type"], flow["side"])
        for key, flow in flows.items()
    } == {
        "nox": ("air", "unspecified", "emission", "output"),
        "dust": ("air", "troposphere, rural", "emission", "output"),
        "ore": ("natural resource", "ground", "natural resource", "input"),
        "wages": ("economic", "unspecified", "economic", "output"),
    }
    named = {compartment["name"] for compartment in listed}
    assert named == {"air", "economic", "natural resource"}
    sub_compartments = {
        sub["name"] for compartment in listed for sub in compartment["sub_compartments"]
    }
    publisher = {"Resource", "Resources", "Emissions to air", "Emission to air", "Economic"}
    assert not (named | sub_compartments) & publisher


def test_factors(client: TestClient) -> None:
    base = f"/api/databases/{FIXTURE_DB}/impact-methods"
    page = client.get(f"{base}/{GWP_ID}/factors").json()["value"]
    assert [(factor["name"], factor["factor"]) for factor in page["items"]] == [
        ("Carbon dioxide, fossil", 1.0),
        ("Methane, fossil", 28.0),
    ]
    assert page["total"] == 2
    narrowed = client.get(f"{base}/{GWP_ID}/factors", params={"query": "methane"}).json()["value"]
    assert names(narrowed) == ["Methane, fossil"]
    assert narrowed["total"] == 1
    size = client.get(f"{base}/{GWP_ID}/factors", params={"limit": "abc"})
    assert size.status_code == 400
    assert "limit" in size.json()["message"]
    unknown = client.get(f"{base}/m_0000000000/factors")
    assert unknown.status_code == 404
    assert "m_0000000000" in unknown.json()["message"]
