from __future__ import annotations

import asyncio
import dataclasses
import getpass
import inspect
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import Client

from ecosemantic import workspace as python_api
from ecosemantic.errors import Invalid, NotFound, NotSupported
from ecosemantic.local import build_context
from ecosemantic.mcp import (
    calculation,
    discovery,
    graph,
    installs,
    modelling,
    parameters,
    requests,
    runs,
    systems,
    tables,
    view,
)
from ecosemantic.mcp.server import ROSTER, build_server
from ecosemantic.model.entities import Actor, Case, Parameter, Uncertainty, method_id
from ecosemantic.model.refs import ForegroundRef, SystemRef
from ecosemantic.ports.types import DatabaseSource, RequestDraft
from ecosemantic.workspace import Database, Process, ProductSystem, Workspace
from tests.fixture_data import FIXTURE_DB, GWP
from tests.memory_installs import MemoryInstaller, MemoryInstalls

GWP_ID = method_id(" > ".join(GWP))
MODULES = [
    discovery,
    systems,
    graph,
    installs,
    tables,
    requests,
    modelling,
    parameters,
    calculation,
    runs,
    view,
]
HELD = {
    Workspace: set(),
    Database: {"database"},
    ProductSystem: {"product_system_id"},
    Process: {"product_system_id", "code"},
}
BROADENED = {"input", "database", "linked"}


@pytest.fixture
def ws(bundle_dir: Path, tmp_path: Path) -> Iterator[Workspace]:
    systems_dir = tmp_path / "python"
    systems_dir.mkdir()
    with python_api.open(bundle_dir, systems_dir) as opened:
        yield opened


def _widget(ws: Workspace) -> tuple[ProductSystem, str]:
    """The fixture's widget through the workspace, with a parameter, a formula and a case; returns
    the system and the id of the frame's steel exchange."""
    db = ws.database(FIXTURE_DB)
    ps = ws.create_product_system("widget", db)
    frame = ps.create_process("frame", "frame production", "kilogram", "frame")
    widget = ps.create_process("widget", "widget assembly", "unit", "widget")
    ps.update_product_system(reference_process="widget")
    ps.set_parameters(
        parameters=[
            Parameter(name="mass", value=2.4),
            Parameter(name="frame_mass", formula="mass * 1.1"),
        ],
        cases=[Case(name="light", values={"mass": 2.0})],
    )
    steel = db.search_processes("steel").items[0]
    co2 = db.search_elementary_flows("carbon dioxide").items[0]
    written = frame.create_exchange("product", formula="frame_mass", input=steel)
    widget.create_exchange("product", amount=0.25, input=frame)
    widget.create_exchange("elementary", amount=0.1, input=co2)
    return ps, str(written.value.id)


async def _widget_through_the_tools(client: Client) -> tuple[str, str]:
    """The same widget through the MCP client; returns the system's id and the steel exchange's."""

    async def call(tool: str, **arguments: object) -> dict:
        return (await client.call_tool(tool, arguments)).structured_content

    made = await call("create_product_system", name="widget", database=FIXTURE_DB)
    sid = made["value"]["id"]
    for code, name, unit in (
        ("frame", "frame production", "kilogram"),
        ("widget", "widget assembly", "unit"),
    ):
        await call(
            "create_process",
            product_system_id=sid,
            code=code,
            name=name,
            unit=unit,
            reference_product=code,
        )
    await call("update_product_system", product_system_id=sid, reference_process="widget")
    await call(
        "set_parameters",
        product_system_id=sid,
        parameters=[
            {"name": "mass", "value": 2.4},
            {"name": "frame_mass", "formula": "mass * 1.1"},
        ],
        cases=[{"name": "light", "values": {"mass": 2.0}}],
    )
    steel = (await call("search_processes", database=FIXTURE_DB, query="steel"))["items"][0]["ref"]
    co2 = (await call("search_elementary_flows", database=FIXTURE_DB, query="carbon dioxide"))[
        "items"
    ][0]["ref"]
    written = await call(
        "create_exchange",
        product_system_id=sid,
        code="frame",
        type="product",
        formula="frame_mass",
        input=steel,
    )
    await call(
        "create_exchange",
        product_system_id=sid,
        code="widget",
        type="product",
        amount=0.25,
        input={"kind": "foreground", "code": "frame"},
    )
    await call(
        "create_exchange",
        product_system_id=sid,
        code="widget",
        type="elementary",
        amount=0.1,
        input=co2,
    )
    return sid, written["value"]["id"]


def _without_system(value: dict) -> dict:
    return {key: item for key, item in value.items() if key != "product_system"}


async def test_the_python_path_and_the_tool_path_answer_alike(
    bundle_dir: Path, tmp_path: Path
) -> None:
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    context = build_context(bundle_dir, tools_dir)
    try:
        async with Client(build_server(context)) as client:
            sid, steel = await _widget_through_the_tools(client)
            overrides = [{"kind": "exchange", "exchange_id": steel, "multiplier": 0.5}]
            await client.call_tool(
                "create_scenario",
                {"product_system_id": sid, "name": "half", "overrides": overrides},
            )
            read = (
                await client.call_tool("get_product_system", {"product_system_id": sid})
            ).structured_content
            report = (
                await client.call_tool("validate_product_system", {"product_system_id": sid})
            ).structured_content
            impact = (
                await client.call_tool(
                    "calculate_impact",
                    {"product_system_id": sid, "method_id": GWP_ID, "variants": ["light", "half"]},
                )
            ).structured_content
    finally:
        context.close()
    python_dir = tmp_path / "python"
    python_dir.mkdir()

    def through_the_workspace() -> tuple[str | None, dict, dict]:
        with python_api.open(bundle_dir, python_dir) as ws:
            ps, exchange = _widget(ws)
            ps.create_scenario(
                "half", overrides=[{"kind": "exchange", "exchange_id": exchange, "multiplier": 0.5}]
            )
            return (
                ps.get_product_system().value.hash,
                ps.validate_product_system().value.model_dump(mode="json"),
                ps.calculate_impact(method_id=GWP_ID, variants=["light", "half"]).value.model_dump(
                    mode="json"
                ),
            )

    hashed, validated, scored = await asyncio.to_thread(through_the_workspace)
    assert hashed == read["value"]["hash"]
    assert validated == report["value"]
    assert _without_system(scored) == _without_system(impact["value"])


def test_a_workspace_s_write_is_logged_as_the_person(ws: Workspace) -> None:
    ps = ws.create_product_system("jar", FIXTURE_DB)
    entry = ps.get_product_system_log().items[0]
    assert entry.actor == Actor(kind="person", name=getpass.getuser())
    assert ps.written is not None and ps.written.entry.actor == entry.actor


def test_a_method_answers_inside_a_running_event_loop(ws: Workspace) -> None:
    async def cell() -> list[str]:
        return [database.name for database in ws.list_databases().value]

    assert FIXTURE_DB in asyncio.run(cell())


def test_close_stops_the_loop_and_its_thread(bundle_dir: Path, tmp_path: Path) -> None:
    opened = python_api.open(bundle_dir, tmp_path)
    thread = opened._thread
    opened.close()
    opened.close()
    assert not thread.is_alive() and opened._loop.is_closed()
    assert all(task.done() for task in opened.context.watchers)


def test_open_takes_this_platform_s_directories_for_those_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("ECOSEMANTIC_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    with python_api.open() as ws:
        assert ws.context.data_dir == tmp_path / "share" / "ecosemantic" / "data"
        assert ws.context.systems_dir == tmp_path / "share" / "ecosemantic" / "systems"


def test_a_typed_error_is_raised_unrendered(ws: Workspace) -> None:
    with pytest.raises(NotFound):
        ws.product_system("00000000-0000-0000-0000-000000000000").get_product_system()


def test_a_handle_or_a_hit_stands_for_the_ref_it_carries(ws: Workspace) -> None:
    db = ws.database(FIXTURE_DB)
    other = ws.create_product_system("frame", db)
    other.create_process("frame", "frame production", "kilogram", "frame")
    other.update_product_system(reference_process="frame")
    ps = ws.create_product_system("widget", db)
    widget = ps.create_process("widget", "widget assembly", "unit", "widget")
    frame = ps.create_process("frame", "frame production", "kilogram", "frame")
    hit = db.search_processes("steel").items[0]
    assert widget.create_exchange("product", amount=1.0, input=frame).value.input == ForegroundRef(
        code="frame"
    )
    assert widget.create_exchange("product", amount=1.0, input=hit).value.input == hit.ref
    linked = widget.create_exchange("product", amount=1.0, input=other).value.input
    assert isinstance(linked, SystemRef) and linked.product_system_id == other.id
    uncertain = frame.create_exchange(
        "product",
        amount=2.0,
        input=hit,
        uncertainty={"type": "lognormal", "params": {"loc": 0.69, "scale": 0.1}},
    )
    assert isinstance(uncertain.value.uncertainty, Uncertainty)


def test_each_method_takes_its_tool_s_arguments() -> None:
    functions = {
        name: getattr(module, name)
        for module in MODULES
        for name in ROSTER
        if hasattr(module, name)
    }
    methods = {
        name: (handle, getattr(handle, name))
        for handle in HELD
        for name in ROSTER
        if hasattr(handle, name)
    }
    assert sorted(methods) == sorted(ROSTER)
    for name, (handle, method) in methods.items():
        tool = [
            parameter
            for parameter in list(inspect.signature(functions[name]).parameters.values())[1:]
            if parameter.name not in HELD[handle]
        ]
        own = list(inspect.signature(method).parameters.values())[1:]
        assert [p.name for p in own] == [p.name for p in tool], name
        assert [p.default for p in own] == [p.default for p in tool], name
        for mine, theirs in zip(own, tool, strict=True):
            if mine.name not in BROADENED:
                assert (
                    mine.annotation.replace("ProcessEntity", "Process").replace(
                        "DatabaseRecord", "Database"
                    )
                    == theirs.annotation
                ), (name, mine.name)


def test_the_install_methods_reach_their_tools(bundle_dir: Path, tmp_path: Path) -> None:
    systems_dir = tmp_path / "installing"
    systems_dir.mkdir()
    context = build_context(bundle_dir, systems_dir, environ={})
    launcher = MemoryInstaller(
        [
            DatabaseSource(
                name="uslci", versions=["2024"], system_models=[], credential=None, terms=False
            )
        ]
    )
    bound = Workspace(
        dataclasses.replace(context, installs=MemoryInstalls(), installer=launcher, view_url=None)
    )
    try:
        assert [source.name for source in bound.list_sources().value] == ["uslci"]
        posted = bound.install_database("uslci").value
        assert posted.pid == 4242
        assert bound.get_install(str(posted.id)).value.id == posted.id
        assert [install.id for install in bound.list_installs().value] == [posted.id]
        assert bound.cancel_install(str(posted.id)).value.cancel_requested is True
    finally:
        bound.close()


def _settled(ws: Workspace, run_id: str) -> str:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        run = ws.get_run(run_id).value
        if not run.open:
            return run.status
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} never settled")


def test_every_method_answers_on_the_fixture_database(
    ws: Workspace, bundle_dir: Path, tmp_path: Path
) -> None:
    db = ws.database(FIXTURE_DB)
    assert FIXTURE_DB in [database.name for database in ws.list_databases().value]
    steel = db.search_processes("steel").items[0]
    co2 = db.search_elementary_flows("carbon dioxide").items[0]
    assert db.search_methods("climate").items
    assert db.get_background_process(steel.ref.id).value.name == steel.name
    assert db.get_elementary_flow(co2.ref.id).value.name == co2.name
    assert db.list_vocabulary("units").value

    ps, exchange = _widget(ws)
    assert ps.id in [card.id for card in ws.list_product_systems().value]
    assert ps.get_product_system().value.reference_process == "widget"
    assert ps.validate_product_system().value.is_valid
    assert ps.get_product_system_log().items
    assert ps.graph_layout().value
    assert ps.arrange_graph([{"code": "frame", "x": 0.0, "y": 0.0}]).value
    assert ps.get_parameters().value
    assert (
        ps.update_exchange(exchange, formula="frame_mass * 1.0").value.formula == "frame_mass * 1.0"
    )
    ps.create_scenario(
        "half", overrides=[{"kind": "exchange", "exchange_id": exchange, "multiplier": 0.5}]
    )
    ps.update_product_system(description="a widget")
    assert ps.rebase_scenario("half").value.name == "half"
    assert ps.calculate_impact(method_id=GWP_ID, variants=["light", "half"]).value.scores
    assert ps.contribution_analysis(method_id=GWP_ID).value
    assert ps.calculate_inventory().items
    with pytest.raises(Invalid, match="already"):
        ps.rebase_database(database=db)
    with pytest.raises(NotSupported):
        ps.view_link()

    done = ps.start_monte_carlo(method_id=GWP_ID, monte_carlo={"n": 3, "n_min": 1, "seed": 7}).value
    assert _settled(ws, str(done.id)) == "done"
    stopped = ps.start_monte_carlo(
        method_id=GWP_ID, monte_carlo={"n": 1000, "n_min": 1, "seed": 7}
    ).value
    ws.cancel_run(str(stopped.id))
    _settled(ws, str(stopped.id))
    assert {str(run.id) for run in ps.list_runs().value} == {str(done.id), str(stopped.id)}

    folder = tmp_path / "tables"
    folder.mkdir()
    exported = ps.export_tables(folder).value
    assert ws.import_tables(exported.path).value

    reviewer = build_context(bundle_dir, ws.context.systems_dir)
    try:
        stated = ps.get_product_system().value.hash
        draft = RequestDraft(
            actor=Actor(kind="person", name="reviewer"),
            kind="return",
            at_hash=stated,
            message="check",
        )
        posted = asyncio.run(reviewer.storage.post_request(ps.id, draft))
    finally:
        reviewer.close()
    assert [request.id for request in ps.list_requests().value] == [posted.id]
    assert ps.resolve_request(str(posted.id), "overridden", "as modelled").value.outcome

    frame_system = ws.create_product_system("frame", db)
    frame_system.create_process("frame", "frame production", "kilogram", "frame")
    frame_system.update_product_system(reference_process="frame")
    linking = ps.process("widget").create_exchange("product", amount=1.0, input=frame_system)
    frame_system.process("frame").update_process(name="frame making")
    assert ps.rebase_links(linked=frame_system).value
    assert ps.delete_exchange(str(linking.value.id)).value

    spare = ps.create_process("spare", "spare part", "kilogram", "spare")
    assert spare.update_process(comment="unused").value.comment == "unused"
    assert spare.delete_process().value == "spare"
    assert ps.delete_scenario("half").value == "half"

    package = tmp_path / "widget.zip"
    ps.export_product_system(package)
    assert ps.delete_product_system().value.id == ps.id
    back = ws.import_product_system(package)
    assert back.id == ps.id and back.written is not None
