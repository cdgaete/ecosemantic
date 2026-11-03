"""The table routes: the folder a person downloads and returns, and a result as a run folder."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from pydantic import JsonValue, TypeAdapter
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from ecosemantic.compute.results import ContributionResult, ImpactResult, InventoryResult
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import as_uuid
from ecosemantic.mcp.tables import apply_tables, result_key, write_tables
from ecosemantic.model.entities import DemandItem
from ecosemantic.package.package import zip_package
from ecosemantic.ports.types import InventoryRow, Page
from ecosemantic.tables.results import (
    ResultKey,
    write_contribution,
    write_impact,
    write_inventory,
)
from ecosemantic.view.api import json_object, structured
from ecosemantic.view.handling import Handler, answering, created, sent, uploaded, working

Payload = dict[str, JsonValue]
Render = Callable[[Path, ResultKey, Payload, datetime], Path]
_DEMAND = TypeAdapter(list[DemandItem])
_NAMES = TypeAdapter(list[str])
_NAME = TypeAdapter(str | None)


def _zipped(folder: Path, work: Path, filename: str) -> FileResponse:
    zipped = work / filename
    zip_package(folder, zipped)
    return sent(zipped, work, filename)


def _impact(work: Path, key: ResultKey, payload: Payload, at: datetime) -> Path:
    return write_impact(work, key, ImpactResult.model_validate(payload["value"]), at)


def _contribution(work: Path, key: ResultKey, payload: Payload, at: datetime) -> Path:
    return write_contribution(work, key, ContributionResult.model_validate(payload["value"]), at)


def _inventory(work: Path, key: ResultKey, payload: Payload, at: datetime) -> Path:
    return write_inventory(
        work,
        key,
        InventoryResult.model_validate(payload),
        Page[InventoryRow].model_validate(payload),
        at,
    )


def routes(server: FastMCP, context: ServerContext) -> list[Route]:
    """The folder download and return, and a run folder for each calculation."""

    @answering
    async def tables_zip(request: Request) -> Response:
        with working("ecosemantic-tables-", keep=True) as work:
            folder, _ = await write_tables(context, as_uuid(request.path_params["id"]), work)
            return _zipped(folder, work, f"{folder.name}.zip")

    @answering
    async def tables_returned(request: Request) -> Response:
        system_id = as_uuid(request.path_params["id"])
        with working("ecosemantic-tables-return-") as work:
            folder, actor = await uploaded(request, "tables", "the edited folder, zipped", work)
            _, _, entry = await apply_tables(context, system_id, folder, actor, "returned tables")
        return created(entry)

    def calculation(tool: str, render: Render, filename: str) -> Handler:
        @answering
        async def handler(request: Request) -> Response:
            body = await json_object(request)
            system_id = as_uuid(request.path_params["id"])
            stored = await context.storage.get_product_system(system_id)
            answered = await structured(server, tool, {"product_system_id": str(system_id), **body})
            key = result_key(
                stored,
                _NAME.validate_python(body.get("method_id")),
                _NAME.validate_python(body.get("impact_method")),
                _DEMAND.validate_python(body.get("demand") or []),
                _NAMES.validate_python(body.get("variants") or []),
            )
            with working("ecosemantic-result-", keep=True) as work:
                folder = await asyncio.to_thread(render, work, key, answered, datetime.now(UTC))
                return _zipped(folder, work, filename)

        return handler

    base = "/api/product-systems/{id}"
    return [
        Route(f"{base}/tables.zip", tables_zip),
        Route(f"{base}/tables", tables_returned, methods=["POST"]),
        Route(
            f"{base}/impact.zip",
            calculation("calculate_impact", _impact, "impact.zip"),
            methods=["POST"],
        ),
        Route(
            f"{base}/contributions.zip",
            calculation("contribution_analysis", _contribution, "contributions.zip"),
            methods=["POST"],
        ),
        Route(
            f"{base}/inventory.zip",
            calculation("calculate_inventory", _inventory, "inventory.zip"),
            methods=["POST"],
        ),
    ]
