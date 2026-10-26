"""A workspace over one data directory and one product systems directory: every tool the MCP server
registers is a method, under the tool's own name, called on the workspace's own event loop and
answered synchronously with the tool's typed answer or its typed error."""

from __future__ import annotations

import asyncio
import functools
import getpass
import threading
import typing
import uuid
from collections.abc import Callable, Coroutine, Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import JsonValue, TypeAdapter

from ecosemantic.compute.edits import ExchangeClearable, ProcessClearable
from ecosemantic.compute.results import ContributionResult, ImpactResult
from ecosemantic.local import build_context, default_directories, defaulted
from ecosemantic.mcp.calculation import (
    ImpactMonteCarlo,
    InventoryListing,
    calculate_impact,
    calculate_inventory,
    contribution_analysis,
)
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.discovery import (
    Kind,
    Term,
    get_background_process,
    get_elementary_flow,
    list_databases,
    list_vocabulary,
    search_elementary_flows,
    search_methods,
    search_processes,
)
from ecosemantic.mcp.envelopes import Answer, Listing, Written, WrittenPath
from ecosemantic.mcp.graph import Arrangement, CardSpot, arrange_graph, graph_layout
from ecosemantic.mcp.installs import (
    cancel_install,
    get_install,
    install_database,
    list_installs,
    list_sources,
)
from ecosemantic.mcp.modelling import (
    create_exchange,
    create_process,
    delete_exchange,
    delete_process,
    rebase_links,
    update_exchange,
    update_process,
)
from ecosemantic.mcp.parameters import (
    ParameterSpace,
    create_scenario,
    delete_scenario,
    get_parameters,
    rebase_scenario,
    set_parameters,
)
from ecosemantic.mcp.requests import list_requests, resolve_request
from ecosemantic.mcp.runs import cancel_run, get_run, list_runs, start_monte_carlo
from ecosemantic.mcp.systems import (
    LOG_PAGE,
    SystemCard,
    SystemRead,
    create_product_system,
    delete_product_system,
    export_product_system,
    get_product_system,
    get_product_system_log,
    import_product_system,
    list_product_systems,
    rebase_database,
    update_product_system,
    validate_product_system,
)
from ecosemantic.mcp.tables import export_tables, import_tables
from ecosemantic.mcp.view import view_link
from ecosemantic.model.entities import (
    Actor,
    Case,
    DemandItem,
    Exchange,
    ExchangeType,
    Method,
    Override,
    Parameter,
    Scenario,
    Uncertainty,
)
from ecosemantic.model.entities import Process as ProcessEntity
from ecosemantic.model.refs import Database as DatabaseRecord
from ecosemantic.model.refs import ExchangeInput, ForegroundRef, SystemRef
from ecosemantic.model.validation import ValidationReport
from ecosemantic.ports.calculation import CUTOFF, MAX_LEVEL, MAX_NODES, TOP_N
from ecosemantic.ports.types import (
    BackgroundProcess,
    DatabaseSource,
    Decomposition,
    ElementaryFlow,
    ElementaryFlowHit,
    FlowType,
    Install,
    LogEntry,
    MonteCarloConfig,
    ProcessHit,
    Request,
    Resolution,
    Run,
    SourceName,
)

T = TypeVar("T")


def open(
    data_dir: Path | None = None,
    systems_dir: Path | None = None,
    solver: str = "superlu",
    actor: Actor | None = None,
) -> Workspace:
    """A workspace over the two directories, this platform's defaults standing for either left
    out, writing as the person running the process unless another actor is named."""
    if data_dir is None or systems_dir is None:
        default_data, default_systems = default_directories()
        data_dir = defaulted(data_dir, default_data)
        systems_dir = defaulted(systems_dir, default_systems)
    writer = actor if actor is not None else Actor(kind="person", name=getpass.getuser())
    return Workspace(build_context(data_dir, systems_dir, actor=writer, solver=solver))


@functools.cache
def _adapters(function: Callable[..., Coroutine[Any, Any, object]]) -> dict[str, TypeAdapter[Any]]:
    hints = typing.get_type_hints(function)
    return {
        name: TypeAdapter(hint) for name, hint in hints.items() if name not in ("context", "return")
    }


def _plain(value: object) -> object:
    """A handle, a search hit or a path as the value a tool takes, through lists and mappings."""
    if isinstance(value, Process):
        return ForegroundRef(code=value.code)
    if isinstance(value, ProductSystem):
        return SystemRef(product_system_id=value.id)
    if isinstance(value, Database):
        return value.name
    if isinstance(value, ProcessHit | ElementaryFlowHit | BackgroundProcess | ElementaryFlow):
        return value.ref
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _id_of(value: str | ProductSystem | None) -> str | None:
    """A product system handle as the id a tool takes; any other value as it is."""
    return str(value.id) if isinstance(value, ProductSystem) else value


class Workspace:
    """The tools that name no product system and no database, and the handles that hold one."""

    def __init__(self, context: ServerContext) -> None:
        self.context = context
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="ecosemantic-workspace", daemon=True
        )
        self._thread.start()
        self._calling = threading.Lock()

    def call(self, function: Callable[..., Coroutine[Any, Any, T]], /, **arguments: object) -> T:
        """The tool function's answer for the arguments, each validated as the tool validates it,
        computed on the workspace's loop; one call at a time."""
        adapters = _adapters(function)
        values = {
            name: adapters[name].validate_python(_plain(value)) for name, value in arguments.items()
        }
        with self._calling:
            return asyncio.run_coroutine_threadsafe(
                function(self.context, **values), self._loop
            ).result()

    def database(self, name: str) -> Database:
        """The handle of an installed database."""
        return Database(self, name)

    def product_system(self, product_system_id: str | uuid.UUID) -> ProductSystem:
        """The handle of a stored product system."""
        return ProductSystem(self, uuid.UUID(str(product_system_id)))

    def close(self) -> None:
        """Stop the run watchers, release what the bound backends hold, and stop the loop."""
        if self._loop.is_closed():
            return

        async def closed() -> None:
            self.context.close()

        asyncio.run_coroutine_threadsafe(closed(), self._loop).result()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_databases(self) -> Answer[list[DatabaseRecord]]:
        """The `list_databases` tool."""
        return self.call(
            list_databases,
        )

    def list_product_systems(self) -> Answer[list[SystemCard]]:
        """The `list_product_systems` tool."""
        return self.call(
            list_product_systems,
        )

    def create_product_system(
        self, name: str, database: str | Database, description: str = "", notes: str = ""
    ) -> ProductSystem:
        """The `create_product_system` tool, answering a handle with its answer in `written`."""
        written = self.call(
            create_product_system,
            name=name,
            database=database,
            description=description,
            notes=notes,
        )
        return ProductSystem(self, written.value.id, written)

    def import_product_system(self, path: str) -> ProductSystem:
        """The `import_product_system` tool, answering a handle with its answer in `written`."""
        written = self.call(import_product_system, path=path)
        return ProductSystem(self, written.value.id, written)

    def import_tables(self, path: str) -> Written[ParameterSpace]:
        """The `import_tables` tool."""
        return self.call(import_tables, path=path)

    def get_run(self, run_id: str) -> Answer[Run]:
        """The `get_run` tool."""
        return self.call(get_run, run_id=run_id)

    def cancel_run(self, run_id: str) -> Answer[Run]:
        """The `cancel_run` tool."""
        return self.call(cancel_run, run_id=run_id)

    def list_sources(self) -> Answer[list[DatabaseSource]]:
        """The `list_sources` tool."""
        return self.call(list_sources)

    def install_database(
        self,
        source: SourceName,
        version: str | None = None,
        system_model: str | None = None,
        replace: bool = False,
        accept_terms: bool = False,
        package: str | None = None,
        name: str | None = None,
        drop_unlinked: bool = False,
    ) -> Answer[Install]:
        """The `install_database` tool."""
        return self.call(
            install_database,
            source=source,
            version=version,
            system_model=system_model,
            replace=replace,
            accept_terms=accept_terms,
            package=package,
            name=name,
            drop_unlinked=drop_unlinked,
        )

    def list_installs(self) -> Answer[list[Install]]:
        """The `list_installs` tool."""
        return self.call(list_installs)

    def get_install(self, install_id: str) -> Answer[Install]:
        """The `get_install` tool."""
        return self.call(get_install, install_id=install_id)

    def cancel_install(self, install_id: str) -> Answer[Install]:
        """The `cancel_install` tool."""
        return self.call(cancel_install, install_id=install_id)


class Database:
    """An installed database: the searches and reads that name it."""

    def __init__(self, workspace: Workspace, name: str) -> None:
        self.workspace = workspace
        self.name = name

    def search_processes(
        self,
        query: str,
        location: str | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Listing[ProcessHit]:
        """The `search_processes` tool."""
        return self.workspace.call(
            search_processes,
            database=self.name,
            query=query,
            location=location,
            unit=unit,
            limit=limit,
            cursor=cursor,
        )

    def search_elementary_flows(
        self,
        query: str,
        compartment: str | None = None,
        sub_compartment: str | None = None,
        flow_type: FlowType | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Listing[ElementaryFlowHit]:
        """The `search_elementary_flows` tool."""
        return self.workspace.call(
            search_elementary_flows,
            database=self.name,
            query=query,
            compartment=compartment,
            sub_compartment=sub_compartment,
            flow_type=flow_type,
            unit=unit,
            limit=limit,
            cursor=cursor,
        )

    def search_methods(
        self, query: str, limit: int = 20, cursor: str | None = None
    ) -> Listing[Method]:
        """The `search_methods` tool."""
        return self.workspace.call(
            search_methods, database=self.name, query=query, limit=limit, cursor=cursor
        )

    def get_background_process(
        self, process_id: str, exchanges: bool = False
    ) -> Answer[BackgroundProcess]:
        """The `get_background_process` tool."""
        return self.workspace.call(
            get_background_process, database=self.name, process_id=process_id, exchanges=exchanges
        )

    def get_elementary_flow(self, flow_id: str) -> Answer[ElementaryFlow]:
        """The `get_elementary_flow` tool."""
        return self.workspace.call(get_elementary_flow, database=self.name, flow_id=flow_id)

    def list_vocabulary(self, kind: Kind) -> Answer[list[Term]]:
        """The `list_vocabulary` tool."""
        return self.workspace.call(list_vocabulary, database=self.name, kind=kind)


class ProductSystem:
    """A stored product system: every tool that names it."""

    def __init__(
        self, workspace: Workspace, id: uuid.UUID, written: Written[SystemCard] | None = None
    ) -> None:
        self.workspace = workspace
        self.id = id
        self.written = written

    def process(self, code: str) -> Process:
        """The handle of one of its processes."""
        return Process(self, code)

    def get_product_system(self, variant: str | None = None) -> SystemRead:
        """The `get_product_system` tool."""
        return self.workspace.call(
            get_product_system, product_system_id=str(self.id), variant=variant
        )

    def update_product_system(
        self,
        name: str | None = None,
        description: str | None = None,
        notes: str | None = None,
        reference_process: str | None = None,
    ) -> Written[SystemCard]:
        """The `update_product_system` tool."""
        return self.workspace.call(
            update_product_system,
            product_system_id=str(self.id),
            name=name,
            description=description,
            notes=notes,
            reference_process=reference_process,
        )

    def delete_product_system(self) -> Answer[SystemCard]:
        """The `delete_product_system` tool."""
        return self.workspace.call(delete_product_system, product_system_id=str(self.id))

    def validate_product_system(self, target: str | None = None) -> Answer[ValidationReport]:
        """The `validate_product_system` tool."""
        return self.workspace.call(
            validate_product_system, product_system_id=str(self.id), target=target
        )

    def export_product_system(self, path: str) -> Answer[WrittenPath]:
        """The `export_product_system` tool."""
        return self.workspace.call(export_product_system, product_system_id=str(self.id), path=path)

    def get_product_system_log(
        self, limit: int = LOG_PAGE, cursor: str | None = None
    ) -> Listing[LogEntry]:
        """The `get_product_system_log` tool."""
        return self.workspace.call(
            get_product_system_log, product_system_id=str(self.id), limit=limit, cursor=cursor
        )

    def graph_layout(self, variant: str | None = None) -> Answer[Arrangement]:
        """The `graph_layout` tool."""
        return self.workspace.call(graph_layout, product_system_id=str(self.id), variant=variant)

    def arrange_graph(
        self,
        placements: list[CardSpot],
        release: list[str] | None = None,
        variant: str | None = None,
    ) -> Answer[Arrangement]:
        """The `arrange_graph` tool."""
        return self.workspace.call(
            arrange_graph,
            product_system_id=str(self.id),
            placements=placements,
            release=release,
            variant=variant,
        )

    def export_tables(self, path: str) -> Answer[WrittenPath]:
        """The `export_tables` tool."""
        return self.workspace.call(export_tables, product_system_id=str(self.id), path=path)

    def list_requests(self, open_only: bool = True) -> Answer[list[Request]]:
        """The `list_requests` tool."""
        return self.workspace.call(
            list_requests, product_system_id=str(self.id), open_only=open_only
        )

    def resolve_request(
        self, request_id: str, resolution: Resolution, message: str
    ) -> Answer[Request]:
        """The `resolve_request` tool."""
        return self.workspace.call(
            resolve_request,
            product_system_id=str(self.id),
            request_id=request_id,
            resolution=resolution,
            message=message,
        )

    def create_process(
        self,
        code: str,
        name: str,
        unit: str,
        reference_product: str,
        location: str = "GLO",
        comment: str | None = None,
        metadata: dict[str, JsonValue] | None = None,
        production_amount: float = 1.0,
    ) -> Process:
        """The `create_process` tool, answering a handle with its answer in `written`."""
        written = self.workspace.call(
            create_process,
            product_system_id=str(self.id),
            code=code,
            name=name,
            unit=unit,
            reference_product=reference_product,
            location=location,
            comment=comment,
            metadata=metadata,
            production_amount=production_amount,
        )
        return Process(self, written.value.code, written)

    def update_exchange(
        self,
        exchange_id: str,
        amount: float | None = None,
        formula: str | None = None,
        name: str | None = None,
        unit: str | None = None,
        comment: str | None = None,
        uncertainty: Uncertainty | None = None,
        clear: list[ExchangeClearable] | None = None,
    ) -> Written[Exchange]:
        """The `update_exchange` tool."""
        return self.workspace.call(
            update_exchange,
            product_system_id=str(self.id),
            exchange_id=exchange_id,
            amount=amount,
            formula=formula,
            name=name,
            unit=unit,
            comment=comment,
            uncertainty=uncertainty,
            clear=clear,
        )

    def delete_exchange(self, exchange_id: str) -> Written[str]:
        """The `delete_exchange` tool."""
        return self.workspace.call(
            delete_exchange, product_system_id=str(self.id), exchange_id=exchange_id
        )

    def rebase_links(self, linked: str | ProductSystem | None = None) -> Written[list[SystemRef]]:
        """The `rebase_links` tool."""
        return self.workspace.call(
            rebase_links, product_system_id=str(self.id), linked=_id_of(linked)
        )

    def get_parameters(self, content_hash: str | None = None) -> Answer[ParameterSpace]:
        """The `get_parameters` tool."""
        return self.workspace.call(
            get_parameters, product_system_id=str(self.id), content_hash=content_hash
        )

    def set_parameters(
        self,
        parameters: list[Parameter] | None = None,
        cases: list[Case] | None = None,
        delete_parameters: list[str] | None = None,
        delete_cases: list[str] | None = None,
    ) -> Written[ParameterSpace]:
        """The `set_parameters` tool."""
        return self.workspace.call(
            set_parameters,
            product_system_id=str(self.id),
            parameters=parameters,
            cases=cases,
            delete_parameters=delete_parameters,
            delete_cases=delete_cases,
        )

    def create_scenario(
        self, name: str, overrides: list[Override], description: str = ""
    ) -> Written[Scenario]:
        """The `create_scenario` tool."""
        return self.workspace.call(
            create_scenario,
            product_system_id=str(self.id),
            name=name,
            overrides=overrides,
            description=description,
        )

    def delete_scenario(self, name: str) -> Written[str]:
        """The `delete_scenario` tool."""
        return self.workspace.call(delete_scenario, product_system_id=str(self.id), name=name)

    def rebase_scenario(self, name: str) -> Written[Scenario]:
        """The `rebase_scenario` tool."""
        return self.workspace.call(rebase_scenario, product_system_id=str(self.id), name=name)

    def calculate_impact(
        self,
        method_id: str | None = None,
        impact_method: str | None = None,
        demand: list[DemandItem] | None = None,
        variants: list[str] | None = None,
        monte_carlo: ImpactMonteCarlo | None = None,
    ) -> Answer[ImpactResult]:
        """The `calculate_impact` tool."""
        return self.workspace.call(
            calculate_impact,
            product_system_id=str(self.id),
            method_id=method_id,
            impact_method=impact_method,
            demand=demand,
            variants=variants,
            monte_carlo=monte_carlo,
        )

    def contribution_analysis(
        self,
        by: Decomposition = "process",
        method_id: str | None = None,
        impact_method: str | None = None,
        demand: list[DemandItem] | None = None,
        top_n: int = TOP_N,
        max_level: int = MAX_LEVEL,
        max_nodes: int = MAX_NODES,
        cutoff: float = CUTOFF,
    ) -> Answer[ContributionResult]:
        """The `contribution_analysis` tool."""
        return self.workspace.call(
            contribution_analysis,
            product_system_id=str(self.id),
            by=by,
            method_id=method_id,
            impact_method=impact_method,
            demand=demand,
            top_n=top_n,
            max_level=max_level,
            max_nodes=max_nodes,
            cutoff=cutoff,
        )

    def calculate_inventory(
        self,
        demand: list[DemandItem] | None = None,
        compartment: str | None = None,
        query: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> InventoryListing:
        """The `calculate_inventory` tool."""
        return self.workspace.call(
            calculate_inventory,
            product_system_id=str(self.id),
            demand=demand,
            compartment=compartment,
            query=query,
            limit=limit,
            cursor=cursor,
        )

    def start_monte_carlo(
        self,
        method_id: str | None = None,
        impact_method: str | None = None,
        demand: list[DemandItem] | None = None,
        monte_carlo: MonteCarloConfig | None = None,
    ) -> Answer[Run]:
        """The `start_monte_carlo` tool."""
        return self.workspace.call(
            start_monte_carlo,
            product_system_id=str(self.id),
            method_id=method_id,
            impact_method=impact_method,
            demand=demand,
            monte_carlo=monte_carlo,
        )

    def list_runs(self) -> Answer[list[Run]]:
        """The `list_runs` tool."""
        return self.workspace.call(list_runs, product_system_id=str(self.id))

    def view_link(self) -> Answer[str]:
        """The `view_link` tool."""
        return self.workspace.call(view_link, product_system_id=str(self.id))

    def rebase_database(self, database: str | Database | None = None) -> Written[SystemCard]:
        """The `rebase_database` tool."""
        return self.workspace.call(
            rebase_database, product_system_id=str(self.id), database=database
        )


class Process:
    """A foreground process of a stored product system: the tools that name it by its code."""

    def __init__(
        self, system: ProductSystem, code: str, written: Written[ProcessEntity] | None = None
    ) -> None:
        self.system = system
        self.code = code
        self.written = written

    def update_process(
        self,
        name: str | None = None,
        unit: str | None = None,
        location: str | None = None,
        reference_product: str | None = None,
        comment: str | None = None,
        metadata: dict[str, JsonValue] | None = None,
        clear: list[ProcessClearable] | None = None,
    ) -> Written[ProcessEntity]:
        """The `update_process` tool."""
        return self.system.workspace.call(
            update_process,
            product_system_id=str(self.system.id),
            code=self.code,
            name=name,
            unit=unit,
            location=location,
            reference_product=reference_product,
            comment=comment,
            metadata=metadata,
            clear=clear,
        )

    def delete_process(self) -> Written[str]:
        """The `delete_process` tool."""
        return self.system.workspace.call(
            delete_process, product_system_id=str(self.system.id), code=self.code
        )

    def create_exchange(
        self,
        type: ExchangeType,
        amount: float | None = None,
        formula: str | None = None,
        unit: str | None = None,
        name: str | None = None,
        input: ExchangeInput
        | Process
        | ProductSystem
        | ProcessHit
        | ElementaryFlowHit
        | Mapping[str, Any]
        | None = None,
        comment: str | None = None,
        uncertainty: Uncertainty | None = None,
    ) -> Written[Exchange]:
        """The `create_exchange` tool."""
        return self.system.workspace.call(
            create_exchange,
            product_system_id=str(self.system.id),
            code=self.code,
            type=type,
            amount=amount,
            formula=formula,
            unit=unit,
            name=name,
            input=input,
            comment=comment,
            uncertainty=uncertainty,
        )
