from __future__ import annotations

from fastmcp import Client, FastMCP
from pydantic import JsonValue

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import INSTRUCTIONS, ROSTER, build_server

CONTRACTS_ORDER = [
    "list_databases",
    "search_processes",
    "search_elementary_flows",
    "search_methods",
    "get_background_process",
    "get_elementary_flow",
    "list_vocabulary",
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
    "graph_layout",
    "arrange_graph",
    "export_tables",
    "import_tables",
    "list_requests",
    "resolve_request",
    "create_process",
    "update_process",
    "delete_process",
    "create_exchange",
    "update_exchange",
    "delete_exchange",
    "rebase_links",
    "get_parameters",
    "set_parameters",
    "create_scenario",
    "delete_scenario",
    "rebase_scenario",
    "calculate_impact",
    "contribution_analysis",
    "calculate_inventory",
    "start_monte_carlo",
    "get_run",
    "list_runs",
    "cancel_run",
]
INSTALLS_ORDER = [
    "list_sources",
    "install_database",
    "list_installs",
    "get_install",
    "cancel_install",
]


async def test_the_roster_is_forty_eight_tools_in_contracts_order(context: ServerContext) -> None:
    server = build_server(context)
    async with Client(server) as client:
        names = [t.name for t in await client.list_tools()]
    assert names == ROSTER
    assert ROSTER == [*CONTRACTS_ORDER, *INSTALLS_ORDER, "view_link"]
    assert len(names) == 48


async def test_no_graph_tool_without_a_backend(context: ServerContext) -> None:
    server = build_server(context)
    async with Client(server) as client:
        assert "graph_query" not in [t.name for t in await client.list_tools()]


async def test_every_tool_describes_itself(context: ServerContext) -> None:
    server = build_server(context)
    async with Client(server) as client:
        for tool in await client.list_tools():
            assert tool.description and len(tool.description) > 30
            assert tool.output_schema is not None


async def test_four_descriptions_state_what_an_agent_learns_only_by_failing(
    context: ServerContext,
) -> None:
    server = build_server(context)
    async with Client(server) as client:
        described = {t.name: t.description or "" for t in await client.list_tools()}
    for name, fact in (
        ("search_processes", "an exact code"),
        ("contribution_analysis", "max_level (default 3)"),
        ("export_product_system", "ecosemantic/log.jsonl"),
        ("create_scenario", "rebase_scenario"),
    ):
        assert fact in described[name], name
        assert "Example: {" in described[name], name


def test_the_instructions_name_the_reference_process_step() -> None:
    assert "update_product_system with reference_process" in INSTRUCTIONS


def _untyped_branches(node: JsonValue, path: str) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key in ("anyOf", "oneOf"):
            branches = node.get(key)
            if isinstance(branches, list):
                for at, branch in enumerate(branches):
                    if isinstance(branch, dict) and not {"type", "$ref", "const"} & set(branch):
                        found.append(f"{path}/{key}/{at}")
        for key, value in node.items():
            found += _untyped_branches(value, f"{path}/{key}")
    elif isinstance(node, list):
        for at, value in enumerate(node):
            found += _untyped_branches(value, f"{path}/{at}")
    return found


async def test_every_alternative_an_argument_offers_names_its_type(
    context: ServerContext,
) -> None:
    # a client that decodes text into an object only where a branch says "object" leaves an
    # untyped branch's value a string, and the call is refused
    server = build_server(context)
    async with Client(server) as client:
        untyped = [
            branch
            for tool in await client.list_tools()
            for branch in _untyped_branches(tool.input_schema, tool.name)
        ]
    assert untyped == []


async def test_the_server_carries_its_identity(context: ServerContext) -> None:
    server: FastMCP = build_server(context)
    assert server.name == "ecosemantic" and server.version
    assert "life cycle" in (server.instructions or "").lower()


class _Rows:
    """A graph backend that echoes the statement it was given as one row."""

    async def query(
        self, database: str, statement: str, parameters: dict[str, JsonValue] | None = None
    ) -> list[dict[str, JsonValue]]:
        return [{"database": database, "statement": statement}]


async def test_a_bound_graph_backend_registers_graph_query_last(context: ServerContext) -> None:
    server = build_server(context, graph=_Rows())
    async with Client(server) as client:
        names = [t.name for t in await client.list_tools()]
        assert names == [*ROSTER, "graph_query"]
        out = await client.call_tool(
            "graph_query", {"database": "g", "statement": "MATCH (n) RETURN n"}
        )
        assert out.structured_content["value"] == [
            {"database": "g", "statement": "MATCH (n) RETURN n"}
        ]


async def test_the_instructions_walk_the_write_path(context: ServerContext) -> None:
    text = build_server(context).instructions or ""
    for name in (
        "list_databases",
        "search_processes",
        "create_product_system",
        "create_process",
        "set_parameters",
        "create_exchange",
        "validate_product_system",
        "search_methods",
        "list_vocabulary",
        "calculate_impact",
        "create_scenario",
        "rebase_scenario",
        "contribution_analysis",
        "calculate_inventory",
        "list_requests",
        "resolve_request",
    ):
        assert name in text
    assert text.index("set_parameters") < text.index("create_exchange")
    assert text.index("validate_product_system") < text.index("calculate_impact")
    assert "open_requests" in text


READ_ONLY = {
    "list_databases",
    "search_processes",
    "search_elementary_flows",
    "search_methods",
    "get_background_process",
    "get_elementary_flow",
    "list_vocabulary",
    "list_product_systems",
    "get_product_system",
    "validate_product_system",
    "get_parameters",
    "export_product_system",
    "export_tables",
    "get_product_system_log",
    "graph_layout",
    "list_requests",
    "calculate_impact",
    "contribution_analysis",
    "calculate_inventory",
    "get_run",
    "list_runs",
    "list_sources",
    "list_installs",
    "get_install",
    "view_link",
}
DESTRUCTIVE = {"delete_product_system", "delete_process", "delete_exchange", "delete_scenario"}


async def test_every_tool_declares_its_effect(context: ServerContext) -> None:
    server = build_server(context, graph=_Rows())
    async with Client(server) as client:
        tools = await client.list_tools()
    assert len(tools) == 49
    for tool in tools:
        hints = tool.annotations
        assert hints is not None, tool.name
        reads = tool.name in READ_ONLY or tool.name == "graph_query"
        assert hints.read_only_hint is reads, tool.name
        assert hints.idempotent_hint is reads, tool.name
        assert hints.destructive_hint is (tool.name in DESTRUCTIVE), tool.name
        assert hints.open_world_hint is False, tool.name


def test_every_tool_is_a_module_function_taking_the_context_first() -> None:
    import inspect

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

    modules = [discovery, systems, graph, tables, requests, modelling, parameters, calculation]
    modules += [runs, installs, view]
    found = {
        name: getattr(module, name)
        for module in modules
        for name in ROSTER
        if inspect.iscoroutinefunction(getattr(module, name, None))
    }
    assert sorted(found) == sorted(ROSTER)
    for name, function in found.items():
        first = next(iter(inspect.signature(function).parameters))
        assert first == "context", name
