from __future__ import annotations

import asyncio
import json
import uuid
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.backends.native.install import install
from ecosemantic.local import build_context
from ecosemantic.mcp import systems
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import ExchangeOverride, ProductSystem, Scenario
from ecosemantic.package.background import read_background
from ecosemantic.ports.types import MonteCarloConfig, RunDraft, RunPatch
from tests.conftest import fixture_system
from tests.engine_fixture import LOOP_DB, install_fixtures
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DB, FIXTURE_FINGERPRINT


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    built = build_server()
    systems.register(built, context)
    return built


@pytest.fixture(scope="module")
async def stored(fixture_system_stored: ProductSystem) -> uuid.UUID:
    return fixture_system_stored.id


async def test_the_roster_is_the_group_in_contracts_order(server: FastMCP) -> None:
    async with Client(server) as client:
        assert [t.name for t in await client.list_tools()] == [
            "list_product_systems",
            "get_product_system",
            "create_product_system",
            "update_product_system",
            "rebase_database",
            "delete_product_system",
            "validate_product_system",
            "export_product_system",
            "import_product_system",
            "get_product_system_log",
        ]


async def test_list_and_get(server: FastMCP, stored: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (await client.call_tool("list_product_systems", {})).structured_content
        assert str(stored) in [s["id"] for s in out["value"]]
        one = (
            await client.call_tool("get_product_system", {"product_system_id": str(stored)})
        ).structured_content["value"]
        assert one["name"] == "widget"
        assert {p["code"] for p in one["processes"]} == {"widget", "frame"}


async def test_log_names_the_first_write(server: FastMCP, stored: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool("get_product_system_log", {"product_system_id": str(stored)})
        ).structured_content["items"]
        assert out[0]["seq"] == 1 and out[0]["message"] == "created"


async def test_validate_reports_each_case(server: FastMCP, stored: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "validate_product_system",
                {"product_system_id": str(stored), "target": "widget"},
            )
        ).structured_content["value"]
        assert out["is_valid"] is True and out["roots"] == ["widget"]
        assert {c["id"] for c in out["cases"]} >= {
            "reference_process_set",
            "no_islands",
            "database_build",
            "treatments_take_waste",
        }


async def test_export_writes_a_model_package(
    server: FastMCP, stored: uuid.UUID, tmp_path: Path
) -> None:
    target = tmp_path / "widget.zip"
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "export_product_system",
                {"product_system_id": str(stored), "path": str(target)},
            )
        ).structured_content["value"]
    assert Path(out["path"]) == target and target.is_file()
    assert len(out["hash"]) == 64
    with zipfile.ZipFile(target) as zipped:
        assert any(n.endswith("olca-schema.json") for n in zipped.namelist())


async def test_an_unknown_id_arrives_as_the_envelope(server: FastMCP) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("get_product_system", {"product_system_id": str(uuid.uuid4())})
        assert json.loads(str(caught.value))["error"] == "not_found"


async def test_create_update_delete_a_product_system(server: FastMCP) -> None:
    async with Client(server) as client:
        made = (
            await client.call_tool(
                "create_product_system",
                {"name": "bottle", "database": FIXTURE_DB, "description": "one bottle"},
            )
        ).structured_content
        assert made["entry"]["seq"] == 1 and made["value"]["database"] == FIXTURE_DB
        system_id = made["value"]["id"]

        patched = (
            await client.call_tool(
                "update_product_system", {"product_system_id": system_id, "notes": "checked"}
            )
        ).structured_content
        assert patched["entry"]["seq"] == 2
        assert patched["entry"]["changes"] == [
            {
                "op": "update",
                "entity": "product_system",
                "id": system_id,
                "field": "notes",
                "before": "",
                "after": "checked",
            }
        ]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        assert whole["notes"] == "checked" and whole["processes"] == []

        gone = (
            await client.call_tool("delete_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        assert gone["id"] == system_id and gone["hash"] == made["entry"]["result_hash"]
        with pytest.raises(ToolError) as caught:
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        assert json.loads(str(caught.value))["error"] == "not_found"


async def test_update_product_system_sets_the_reference_and_logs_it(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        await client.call_tool(
            "create_process",
            {
                "product_system_id": bottle,
                "code": "bottle",
                "name": "bottle",
                "unit": "kilogram",
                "reference_product": "bottle",
            },
        )
        out = await client.call_tool(
            "update_product_system", {"product_system_id": bottle, "reference_process": "bottle"}
        )
        system = await client.call_tool("get_product_system", {"product_system_id": bottle})
        with pytest.raises(ToolError, match="names no process"):
            await client.call_tool(
                "update_product_system", {"product_system_id": bottle, "reference_process": "cap"}
            )
    assert out.structured_content["entry"]["changes"] == [
        {
            "op": "update",
            "entity": "product_system",
            "id": bottle,
            "field": "reference_process",
            "before": None,
            "after": "bottle",
        }
    ]
    assert system.structured_content["value"]["reference_process"] == "bottle"


async def test_an_unknown_database_is_not_found(server: FastMCP) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("create_product_system", {"name": "x", "database": "nothing"})
        payload = json.loads(str(caught.value))
        assert payload["error"] == "not_found" and FIXTURE_DB in payload["message"]


async def test_an_empty_patch_is_invalid(server: FastMCP, stored: uuid.UUID) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("update_product_system", {"product_system_id": str(stored)})
        assert json.loads(str(caught.value))["error"] == "invalid"


async def test_create_stamps_the_installed_build_and_export_carries_it(
    server: FastMCP, context: ServerContext, tmp_path: Path
) -> None:
    installed = await context.inventory.get_database(FIXTURE_DB)
    assert installed.fingerprint is not None
    async with Client(server) as client:
        made = (
            await client.call_tool("create_product_system", {"name": "cup", "database": FIXTURE_DB})
        ).structured_content
        system_id = made["value"]["id"]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        assert whole["database"]["fingerprint"] == installed.fingerprint
        zipped = tmp_path / "cup.zip"
        await client.call_tool(
            "export_product_system", {"product_system_id": system_id, "path": str(zipped)}
        )
        await client.call_tool("delete_product_system", {"product_system_id": system_id})
        await client.call_tool("import_product_system", {"path": str(zipped)})
        back = (
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        assert back["database"]["fingerprint"] == installed.fingerprint


async def test_import_refuses_a_stored_id_and_restores_a_deleted_one(
    server: FastMCP, tmp_path: Path
) -> None:
    async with Client(server) as client:
        made = (
            await client.call_tool("create_product_system", {"name": "jar", "database": FIXTURE_DB})
        ).structured_content
        system_id = made["value"]["id"]
        zipped = tmp_path / "jar.zip"
        await client.call_tool(
            "export_product_system", {"product_system_id": system_id, "path": str(zipped)}
        )

        with pytest.raises(ToolError) as caught:
            await client.call_tool("import_product_system", {"path": str(zipped)})
        payload = json.loads(str(caught.value))
        assert payload["error"] == "conflict"
        assert f"product system {system_id} is stored already" in payload["message"]

        await client.call_tool("delete_product_system", {"product_system_id": system_id})
        back = (
            await client.call_tool("import_product_system", {"path": str(zipped)})
        ).structured_content
        assert back["value"]["id"] == system_id and back["value"]["name"] == "jar"
        assert back["entry"]["seq"] == 1 and back["entry"]["source"] == "import"
        log = (
            await client.call_tool("get_product_system_log", {"product_system_id": system_id})
        ).structured_content["items"]
        assert [e["source"] for e in log] == ["import"]


async def test_parallel_imports_of_one_native_store_it_once(
    server: FastMCP, tmp_path: Path
) -> None:
    async with Client(server) as client:
        made = (
            await client.call_tool("create_product_system", {"name": "jug", "database": FIXTURE_DB})
        ).structured_content
        system_id = made["value"]["id"]
        zipped = tmp_path / "jug.zip"
        await client.call_tool(
            "export_product_system", {"product_system_id": system_id, "path": str(zipped)}
        )
        await client.call_tool("delete_product_system", {"product_system_id": system_id})
        answers = await asyncio.gather(
            *(
                client.call_tool(
                    "import_product_system", {"path": str(zipped)}, raise_on_error=False
                )
                for _ in range(4)
            )
        )
        outcomes = sorted(
            json.loads(a.content[0].text)["error"] if a.is_error else "stored" for a in answers
        )
        assert outcomes == ["conflict", "conflict", "conflict", "stored"]
        log = (
            await client.call_tool("get_product_system_log", {"product_system_id": system_id})
        ).structured_content["items"]
        assert [e["source"] for e in log] == ["import"]


async def test_export_carries_each_linked_system_at_its_pin(
    server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem], tmp_path: Path
) -> None:
    widget, frame = linked_stored
    zipped = tmp_path / "widget.zip"
    async with Client(server) as client:
        await client.call_tool(
            "export_product_system", {"product_system_id": str(widget.id), "path": str(zipped)}
        )
    names = zipfile.ZipFile(zipped).namelist()
    assert f"linked/{frame.id}/ecosemantic/product_system.json" in names
    assert f"product_systems/{frame.id}.json" in names


async def test_import_of_a_missing_file_is_invalid(server: FastMCP, tmp_path: Path) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("import_product_system", {"path": str(tmp_path / "no.zip")})
        assert json.loads(str(caught.value))["error"] == "invalid"


async def test_validate_without_a_target_fails_while_no_reference_is_set(
    server: FastMCP, bottle: str
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool("validate_product_system", {"product_system_id": bottle})
        ).structured_content["value"]
    assert out["is_valid"] is False and out["target"] is None and out["roots"] == []
    [issue] = [e for e in out["errors"] if e["code"] == "reference_process_missing"]
    # an empty system has no single root to suggest
    assert issue["suggestion"] == (
        "set reference_process to the process whose product is the functional unit"
    )


async def test_create_on_the_flows_name_resolves_to_the_owner(server: FastMCP) -> None:
    async with Client(server) as client:
        made = (
            await client.call_tool(
                "create_product_system", {"name": "tin", "database": FIXTURE_BIO}
            )
        ).structured_content
        assert made["value"]["database"] == FIXTURE_DB


async def test_deleting_a_product_system_removes_its_runs(
    full_server: FastMCP, context: ServerContext
) -> None:
    async with Client(full_server) as client:
        made = await client.call_tool(
            "create_product_system", {"name": "short_lived", "database": FIXTURE_DB}
        )
        system_id = uuid.UUID(made.structured_content["value"]["id"])
        run = await context.runs.post_run(
            RunDraft(
                product_system_id=system_id,
                at_hash="0" * 64,
                demand=[],
                methods=[],
                config=MonteCarloConfig(),
            )
        )
        await context.runs.update_run(run.id, RunPatch(status="done"))
        await client.call_tool("delete_product_system", {"product_system_id": str(system_id)})
        listed = await client.call_tool("list_runs", {"product_system_id": str(system_id)})
    assert listed.structured_content["value"] == []


async def test_rebase_database_moves_a_system_onto_the_installed_build(
    server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "rebased")
    system.name = "widget_rebased"
    system.database = system.database.model_copy(update={"fingerprint": None})
    steel = system.process("widget").exchanges[1]
    system.scenarios = [
        Scenario(
            name="doubled",
            overrides=[ExchangeOverride(exchange_id=steel.id, multiplier=2.0)],
            base_hash=base_pin(system),
        )
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    installed = await context.inventory.get_database(FIXTURE_DB)
    assert installed.fingerprint is not None
    async with Client(server) as client:
        moved = (
            await client.call_tool("rebase_database", {"product_system_id": str(system.id)})
        ).structured_content
        assert moved["entry"]["message"] == (
            f"moved product system widget_rebased from 'fixture' at no build to 'fixture' at "
            f"build {installed.fingerprint[:12]}"
        )
        assert moved["consequences"]["scenarios_staled"] == ["doubled"]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": str(system.id)})
        ).structured_content["value"]
        assert whole["database"]["fingerprint"] == installed.fingerprint
        with pytest.raises(ToolError) as caught:
            await client.call_tool("rebase_database", {"product_system_id": str(system.id)})
        assert json.loads(str(caught.value))["error"] == "invalid"


@pytest.fixture(scope="module")
async def renamed(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[ServerContext]:
    """The fixture bundle installed twice, as fixture and as fixture-copy, beside the looped
    background."""
    data = tmp_path_factory.mktemp("renamed")
    sources = tmp_path_factory.mktemp("renamed-sources")
    install_fixtures(data, sources)
    bundle = sources / "fixture.zip"
    copy = read_background(bundle, "fixture-copy", foreground=frozenset())
    install(data, copy, bundle, version="1", system_model="unit process")
    built = build_context(data, tmp_path_factory.mktemp("renamed-systems"))
    yield built
    built.close()


async def test_rebase_database_onto_a_renamed_install_keeps_every_score(
    renamed: ServerContext,
) -> None:
    system = fixture_system().product_system
    assert system is not None
    await renamed.storage.put_product_system(system, renamed.actor, "created")
    args = {"product_system_id": str(system.id), "impact_method": "gwp"}
    async with Client(build_server(renamed)) as client:
        before = (await client.call_tool("calculate_impact", args)).structured_content["value"]
        moved = (
            await client.call_tool(
                "rebase_database",
                {"product_system_id": str(system.id), "database": "fixture-copy"},
            )
        ).structured_content
        after = (await client.call_tool("calculate_impact", args)).structured_content["value"]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": str(system.id)})
        ).structured_content["value"]
    # one build installed under another name keeps its fingerprint
    copy = await renamed.inventory.get_database("fixture-copy")
    assert copy.fingerprint == FIXTURE_FINGERPRINT
    assert moved["entry"]["message"] == (
        f"moved product system widget from 'fixture' at build {FIXTURE_FINGERPRINT[:12]} to "
        f"'fixture-copy' at build {FIXTURE_FINGERPRINT[:12]}"
    )
    assert [s["value"] for s in after["scores"]] == [s["value"] for s in before["scores"]]
    assert after["database"] == copy.model_dump(mode="json")
    inputs = [e["input"] for p in whole["processes"] for e in p["exchanges"] if e["input"]]
    assert {i["database"] for i in inputs if i["kind"] == "background"} == {"fixture-copy"}
    assert {i["database"] for i in inputs if i["kind"] == "elementary_flow"} == {
        "fixture-copy-biosphere"
    }


async def test_rebase_database_onto_a_database_lacking_references_writes_nothing(
    renamed: ServerContext,
) -> None:
    system = fixture_system().product_system
    assert system is not None
    system = system.model_copy(update={"id": uuid.uuid5(system.id, "lacking"), "name": "lacking"})
    await renamed.storage.put_product_system(system, renamed.actor, "created")
    async with Client(build_server(renamed)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "rebase_database", {"product_system_id": str(system.id), "database": LOOP_DB}
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "not_found"
    assert payload["message"].startswith(f"{LOOP_DB!r} lacks 3 references lacking names:")
    widget = system.process("widget")
    steel = next(e for e in widget.exchanges if e.name == "steel")
    assert f"widget · steel · {steel.input.id}" in payload["message"]  # type: ignore[union-attr]
    assert len(await renamed.storage.log(system.id)) == 1
