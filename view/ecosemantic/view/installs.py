"""The page's routes over the install tools: the sources, the installs, the terms file an install
stopped at, and the openLCA zip a person uploads."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastmcp import FastMCP
from starlette.datastructures import FormData, UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import Answer
from ecosemantic.ports.types import Install
from ecosemantic.view.api import call_tool, json_object, structured
from ecosemantic.view.handling import answering, refuse_oversized, zip_entries

DATABASE_UPLOAD_BYTES = 4_000_000_000
CHUNK_BYTES = 1_000_000
CARRIES = "the openLCA zip"


def _stated(form: FormData, field: str) -> str | None:
    """A form's text field, None when the form carries none."""
    value = form.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, UploadFile):
        raise Invalid(f"the form field {field!r} carries a file")
    return value


def _flag(form: FormData, field: str) -> bool:
    """A form's checkbox: true or false, Invalid for a value that is neither."""
    stated = _stated(form, field)
    if stated is None or stated.casefold() == "false":
        return False
    if stated.casefold() == "true":
        return True
    raise Invalid(f"the form field {field!r} is {stated!r}, not true or false")


async def _stored(upload: UploadFile, target: Path) -> None:
    """Write an uploaded file to the target in chunks, Invalid once it passes the bytes a database
    upload may hold."""
    written = 0
    with target.open("wb") as out:
        while chunk := await upload.read(CHUNK_BYTES):
            written += len(chunk)
            refuse_oversized(CARRIES, written, DATABASE_UPLOAD_BYTES)
            out.write(chunk)


def routes(server: FastMCP, context: ServerContext) -> list[Route]:
    """The sources and the installs, the terms file, and the zip an openLCA install reads."""

    async def sources(request: Request) -> Response:
        return await call_tool(server, "list_sources", {})

    async def posted(request: Request) -> Response:
        return await call_tool(server, "install_database", await json_object(request))

    async def listed(request: Request) -> Response:
        return await call_tool(server, "list_installs", {})

    async def read(request: Request) -> Response:
        return await call_tool(server, "get_install", {"install_id": request.path_params["id"]})

    async def cancelled(request: Request) -> Response:
        return await call_tool(server, "cancel_install", {"install_id": request.path_params["id"]})

    @answering
    async def licence(request: Request) -> Response:
        """The terms file of the install the request names, NotFound when it stopped at none."""
        install = Answer[Install].model_validate(
            await structured(server, "get_install", {"install_id": request.path_params["id"]})
        )
        terms = install.value.terms
        if terms is None:
            raise NotFound(f"install {install.value.id} stopped at no terms")
        return FileResponse(terms.licence)

    @answering
    async def openlca(request: Request) -> Response:
        """The zip a person holds, streamed under the uploads directory and posted as an openLCA
        install reading it. An upload refused as not a zip, cut short or past the limit is
        deleted, and so is one whose install the server refuses."""
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise Invalid(f"the form field 'file' carries {CARRIES}")
        draft = {
            "source": "openlca",
            "name": _stated(form, "name"),
            "version": _stated(form, "version"),
            "system_model": _stated(form, "system_model"),
            "replace": _flag(form, "replace"),
            "drop_unlinked": _flag(form, "drop_unlinked"),
        }
        zipped = context.uploads_dir / f"{uuid.uuid4()}.zip"
        zipped.parent.mkdir(parents=True, exist_ok=True)
        try:
            await _stored(upload, zipped)
            zip_entries(zipped, CARRIES)
        except BaseException:
            zipped.unlink(missing_ok=True)
            raise
        answered = await call_tool(server, "install_database", {**draft, "package": str(zipped)})
        if answered.status_code >= 400:
            zipped.unlink(missing_ok=True)
        return answered

    return [
        Route("/api/sources", sources),
        Route("/api/installs", posted, methods=["POST"]),
        Route("/api/installs", listed),
        Route("/api/installs/openlca", openlca, methods=["POST"]),
        Route("/api/installs/{id}", read),
        Route("/api/installs/{id}/cancel", cancelled, methods=["POST"]),
        Route("/api/installs/{id}/licence", licence),
    ]
