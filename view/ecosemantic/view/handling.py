"""What every route handler of the view shares: the caller it answers for, its error boundary,
a working directory, an uploaded zip and a download that cleans up after itself."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import shutil
import tempfile
import zipfile
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from ecosemantic.errors import (
    EcoSemanticError,
    ErrorEnvelope,
    Invalid,
    error_payload,
    error_status,
)
from ecosemantic.mcp.callers import resolved
from ecosemantic.mcp.context import Callers, ServerContext
from ecosemantic.model.entities import ProductSystem
from ecosemantic.package.package import unzip_package
from ecosemantic.tables.folder import folder_name

Handler = Callable[[Request], Awaitable[Response]]
ContextHandler = Callable[[Request, ServerContext], Awaitable[Response]]
DownloadContent = Literal["impact", "contributions", "inventory", "tables", "openlca"]
UPLOAD_BYTES = 100_000_000
UNPACKED_BYTES = 1_000_000_000
UNPACKED_ENTRIES = 100_000


def envelope_response(envelope: ErrorEnvelope) -> JSONResponse:
    """An error envelope as the response that carries it, under its kind's HTTP status."""
    return JSONResponse(envelope.model_dump(mode="json"), status_code=error_status(envelope.error))


def error_response(exc: EcoSemanticError) -> JSONResponse:
    """A typed error as the envelope the tools return, under its HTTP status."""
    return envelope_response(error_payload(exc))


def created(made: BaseModel) -> JSONResponse:
    """What a write made, as the 201 that answers it."""
    return JSONResponse(made.model_dump(mode="json"), status_code=201)


class Unchanged(BaseModel):
    """A return that left the stored state as it stood."""

    message: str


def unchanged(message: str) -> JSONResponse:
    """A return that wrote nothing, as the 200 that answers it with the words that say so."""
    return JSONResponse(Unchanged(message=message).model_dump(mode="json"))


class ToolRefused(Exception):
    """A tool call that did not answer, carrying the response a route answers it with."""

    def __init__(self, response: JSONResponse) -> None:
        super().__init__("the tool call did not answer")
        self.response = response


def answering(handler: Handler) -> Handler:
    """The view's one boundary: a handler whose typed errors and refused tool calls answer as
    their envelopes. Nothing below a handler catches either."""

    @functools.wraps(handler)
    async def call(request: Request) -> Response:
        try:
            return await handler(request)
        except EcoSemanticError as exc:
            return error_response(exc)
        except ToolRefused as refused:
            return refused.response

    return call


def for_caller(callers: Callers) -> Callable[[ContextHandler], Handler]:
    """The view's caller seam: a handler given the context the host binds to its request's caller,
    resolved before the handler reads a body, a form or a path parameter, and answered as
    `answering` answers."""

    def wrapping(handler: ContextHandler) -> Handler:
        @functools.wraps(handler)
        async def call(request: Request) -> Response:
            return await handler(request, await resolved(callers, request.scope))

        return answering(call)

    return wrapping


@contextlib.contextmanager
def working(prefix: str, keep: bool = False) -> Iterator[Path]:
    """A temporary directory for one request, removed on the way out. A kept one is removed only
    when the request fails, because the download it serves removes it once it is sent."""
    work = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield work
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def refuse_oversized(carries: str, size: int, limit: int) -> None:
    """Invalid for a file larger than the bytes an upload holds, naming its size and the limit."""
    if size > limit:
        raise Invalid(f"{carries} is {size} bytes; an upload holds at most {limit}")


def zip_entries(upload: Path, carries: str) -> list[zipfile.ZipInfo]:
    """The entries a zip file holds, read from its directory; Invalid when the file is not a zip
    file at all, one cut short included."""
    try:
        with zipfile.ZipFile(upload) as zipped:
            return zipped.infolist()
    except zipfile.BadZipFile as error:
        raise Invalid(f"{carries} is not a zip file") from error


def _refuse_unpackable(upload: Path, carries: str) -> None:
    """Invalid for a zip whose entries exceed the count or the unpacked size an upload may hold,
    read from its directory before anything is unpacked."""
    entries = zip_entries(upload, carries)
    if len(entries) > UNPACKED_ENTRIES:
        raise Invalid(
            f"{carries} holds {len(entries)} entries; an upload holds at most {UNPACKED_ENTRIES}"
        )
    size = sum(entry.file_size for entry in entries)
    if size > UNPACKED_BYTES:
        raise Invalid(
            f"{carries} unpacks to {size} bytes; an upload unpacks to at most {UNPACKED_BYTES}"
        )


async def uploaded(request: Request, field: str, carries: str, work: Path) -> tuple[Path, str]:
    """The zip a form carries under a field, unpacked under the working directory, and the text
    the form states as the person who posted it; Invalid when the field holds no file, and for a
    file past the size, the unpacked size or the entry count an upload may hold."""
    form = await request.form()
    upload = form.get(field)
    if not isinstance(upload, UploadFile):
        raise Invalid(f"the form field {field!r} carries {carries}")
    content = await upload.read()
    refuse_oversized(carries, len(content), UPLOAD_BYTES)
    zipped = work / "returned.zip"
    zipped.write_bytes(content)
    _refuse_unpackable(zipped, carries)
    unpacked = work / "unpacked"
    await asyncio.to_thread(unzip_package, zipped, unpacked)
    return unpacked, str(form.get("actor", ""))


def download_name(system: ProductSystem, content: DownloadContent) -> str:
    """The file name a download takes: the system's folder name and the content it carries."""
    return f"{folder_name(system)}-{content}.zip"


def sent(zipped: Path, work: Path, filename: str) -> FileResponse:
    """A zip file as a download that removes its working directory once it is sent."""
    return FileResponse(
        zipped,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )
