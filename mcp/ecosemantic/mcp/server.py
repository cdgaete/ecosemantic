"""The stdio MCP server: what it is called, what it registers, and in what order."""

from __future__ import annotations

from importlib.metadata import version

from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.types import InitializeRequest, InitializeResult
from opentelemetry.metrics import MeterProvider, NoOpMeterProvider
from pydantic import JsonValue

from ecosemantic.mcp import (
    calculation,
    discovery,
    guides,
    installs,
    modelling,
    panels,
    parameters,
    requests,
    runs,
    systems,
    tables,
    view,
)
from ecosemantic.mcp import graph as graph_tools
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.counting import Counting
from ecosemantic.mcp.effects import READ
from ecosemantic.mcp.envelopes import Answer, ArgumentRefusal, boundary
from ecosemantic.mcp.recording import Recorder
from ecosemantic.ports.graph import GraphQueryPort

INSTRUCTIONS = (
    "Life cycle assessment over background databases installed on this machine from database "
    "bundles.\n"
    "\n"
    "Read. list_databases names the background databases and, for each, the elementary_flows "
    "database its flow refs carry. search_processes, search_elementary_flows and "
    "search_methods take a database and a query of at least one term; every hit carries a ref, "
    "and a ref is passed on verbatim. A ref, an uncertainty, a demand item or an override is a "
    "JSON object in the call, never a string holding JSON. list_vocabulary lists a database's "
    "units, locations, compartments, impact_methods and impact_categories: the exact spellings "
    "the filters take.\n"
    "\n"
    "Install. list_sources names every source a background database comes from, with the versions "
    "and system models it offers, whether it has terms and whether this server holds the account "
    "its install needs. install_database posts one: source, with version and system_model for a "
    "source this package builds, or package, name, version and system_model for an openlca zip. "
    "A source with terms stops at them until accept_terms is passed on the person's word, and a "
    "credential is "
    "entered by the person on the page, never in a call here. list_installs and get_install "
    "follow the install, cancel_install asks it to stop, and list_databases names the database "
    "once the install is done.\n"
    "\n"
    "Model, in this order. create_product_system on one database. create_process, which "
    "writes the production exchange. update_product_system with reference_process names the "
    "process whose product is the functional unit; validation without a target and "
    "calculation without a demand need it. set_parameters before any formula names a "
    "parameter. "
    "create_exchange on a process by code, with the ref a search hit carries and an amount or "
    "a formula. validate_product_system until it reports valid.\n"
    "\n"
    "Calculate. calculate_impact takes a method_id from search_methods or an impact_method "
    "family from list_vocabulary, and runs at most 200 draws in the call; "
    "start_monte_carlo runs up to 1000 outside it. A product system's hash is the content "
    "hash, over its processes, exchanges, parameters, cases, reference process and database "
    "build; its name, description, scenarios and layout are in no hash, so two empty systems "
    "of different names share one. create_scenario pins a what-if to the base hash, the same "
    "projection without the cases and the build, so a case written or deleted moves no "
    "scenario and a scenario's base_hash is never a system's hash; after any later edit, "
    "rebase_scenario before naming it as a variant, and validate_product_system says whether "
    "each scenario is current. create_exchange with a "
    "system input links another product system's functional unit, pinned to its current "
    "state; after that system changes, rebase_links moves the pin. A calculation refuses a "
    "system that names a build of its database other than the installed one, or none; "
    "rebase_database moves it onto the installed build. contribution_analysis "
    "decomposes one score by process, by path or by flow; calculate_inventory pages every "
    "elementary flow.\n"
    "\n"
    "Every write appends one entry to the product system's log and returns it. A call that "
    "cannot do what was asked raises a typed error naming the remedy.\n"
    "\n"
    "Draw. graph_layout reads where every card of a product system sits, as a map in "
    "characters beside the exact numbers; arrange_graph puts named cards elsewhere and holds "
    "them there, as a person dragging one does.\n"
    "\n"
    "Guides. Three resources hold a short checklist and a worked example each; read one before "
    "the task it names: guide://ecosemantic/building-a-model, "
    "guide://ecosemantic/interpreting-a-result and guide://ecosemantic/sensitivity-study."
)

REVIEW = (
    "Review. A person may watch the model in a browser and post requests there. Every write "
    "answers with open_requests, the number of return or edit requests without an outcome; "
    "list_requests reads them. Answer a request in the conversation, then resolve_request "
    "records accepted, with the fix as the next write, or overridden, with the reason."
)


def instructions_for(context: ServerContext | None) -> str:
    """The instructions, with the page's link when the server serves one."""
    text = f"{INSTRUCTIONS}\n\n{REVIEW}"
    if context is not None and context.view_url is not None:
        text += (
            f" The person can watch the model at {context.view_url}; give them that link in "
            "your first reply."
        )
    return text


ROSTER = [
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
    "list_sources",
    "install_database",
    "list_installs",
    "get_install",
    "cancel_install",
    "view_link",
]


class Introducing(Middleware):
    """Keeps the name and the version of the client that introduced itself to this server."""

    def __init__(self, client: dict[str, str]) -> None:
        self.client = client

    async def on_initialize(
        self,
        context: MiddlewareContext[InitializeRequest],
        call_next: CallNext[InitializeRequest, InitializeResult | None],
    ) -> InitializeResult | None:
        info = context.message.params.client_info
        self.client.update({"name": info.name, "version": info.version})
        return await call_next(context)


def build_server(
    context: ServerContext | None = None,
    graph: GraphQueryPort | None = None,
    meter_provider: MeterProvider | None = None,
) -> FastMCP:
    """The server with its tools registered in roster order; no context registers none."""
    server = FastMCP(
        name="ecosemantic",
        version=version("ecosemantic-mcp"),
        instructions=instructions_for(context),
        middleware=(
            [
                Counting(ROSTER, meter_provider or NoOpMeterProvider()),
                Introducing(context.client),
                Recorder(context.activity, context.storage, context.events, context.agent),
            ]
            if context is not None
            else []
        ),
    )
    if context is None:
        return server
    server.add_middleware(ArgumentRefusal(server))
    discovery.register(server, context)
    systems.register(server, context)
    graph_tools.register(server, context)
    tables.register(server, context)
    requests.register(server, context)
    modelling.register(server, context)
    parameters.register(server, context)
    calculation.register(server, context)
    runs.register(server, context)
    installs.register(server, context)
    panels.register(server)
    guides.register(server)
    view.register(server, context)
    if graph is not None:
        _register_graph(server, graph)
    return server


def _register_graph(server: FastMCP, graph: GraphQueryPort) -> None:
    @server.tool(
        name="graph_query",
        annotations=READ,
        description="Run a statement against the deployment's graph store and return its rows.",
    )
    @boundary
    async def graph_query(database: str, statement: str) -> Answer[list[dict[str, JsonValue]]]:
        return Answer[list[dict[str, JsonValue]]](value=await graph.query(database, statement))
