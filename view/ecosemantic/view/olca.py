"""The openLCA hand-off: the package to download, and the export openLCA returns."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ecosemantic.errors import Invalid
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import as_uuid
from ecosemantic.mcp.systems import export_package
from ecosemantic.view.handling import answering, created, sent, uploaded, working


def _entry_of(stated: object) -> int | None:
    """The log entry a return form states; None when it states none, Invalid for a value that
    is no entry number."""
    if not isinstance(stated, str) or stated == "":
        return None
    if not stated.isdecimal():
        raise Invalid(f"at_entry {stated!r} is no entry number")
    return int(stated)


def routes(context: ServerContext) -> list[Route]:
    """The download and the return."""

    @answering
    async def package_zip(request: Request) -> Response:
        system_id = as_uuid(request.path_params["id"])
        with working("ecosemantic-export-", keep=True) as work:
            zipped = work / f"{system_id}.zip"
            system, _ = await export_package(context, system_id, zipped)
            return sent(zipped, work, f"{system.name}.zip")

    @answering
    async def returned(request: Request) -> Response:
        system_id = as_uuid(request.path_params["id"])
        with working("ecosemantic-return-") as work:
            exported, actor = await uploaded(request, "package", "the exported zip", work)
            at_entry = _entry_of((await request.form()).get("at_entry"))
            entry = await context.storage.return_package(system_id, exported, actor, at_entry)
        return created(entry)

    return [
        Route("/api/product-systems/{id}/package.zip", package_zip),
        Route("/api/product-systems/{id}/return", returned, methods=["POST"]),
    ]
