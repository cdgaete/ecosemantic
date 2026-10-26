"""The install tools: the sources a database comes from, and the install posted, followed and
cancelled."""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from ecosemantic.compute.accounts import missing
from ecosemantic.errors import Conflict, Unavailable
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ, WRITE
from ecosemantic.mcp.envelopes import Answer, as_uuid, bound, boundary
from ecosemantic.mcp.watcher import reap_install, watch_install
from ecosemantic.ports.types import (
    DatabaseSource,
    Install,
    InstallDraft,
    InstallPatch,
    SourceName,
    source_credential,
)


def databases_link(context: ServerContext) -> str | None:
    """The Databases editor that shows the sources and the installs."""
    return context.page_at("/databases")


def held_sources(context: ServerContext) -> list[DatabaseSource]:
    """Every source an install may come from, each saying whether the account it needs is one
    this server holds."""
    return [
        source.model_copy(
            update={
                "held": source.credential is None or source.credential in context.credentials,
            }
        )
        for source in context.installer.sources()
    ]


async def list_sources(context: ServerContext) -> Answer[list[DatabaseSource]]:
    """Every source a database installs from, with the versions its profiles pin, what its
    install needs, and whether this server holds the account it needs. It never answers a
    credential."""
    return Answer[list[DatabaseSource]](
        value=held_sources(context), view_url=databases_link(context)
    )


async def install_database(
    context: ServerContext,
    source: SourceName,
    version: str | None = None,
    system_model: str | None = None,
    replace: bool = False,
    accept_terms: bool = False,
    package: str | None = None,
    name: str | None = None,
    drop_unlinked: bool = False,
) -> Answer[Install]:
    """Post an install from a source and start the process that carries it, apart from this
    server so a restart does not stop it. list_installs and get_install follow it, cancel_install
    asks it to stop. One install at a time: a second is refused while one is open."""
    needed = source_credential(source)
    account = context.credentials.get(needed) if needed is not None else None
    if needed is not None and account is None:
        raise Unavailable(
            f"{source} installs from an account this server does not hold",
            hint=f"{missing(needed)}: {context.page_at('/databases')}",
        )
    async with context.installs.slot():
        for existing in await context.installs.list_installs():
            settled = await reap_install(context.installs, context.installer, existing)
            if settled.open:
                raise Conflict(f"install {settled.id} is still {settled.status}")
        posted = await context.installs.post_install(
            InstallDraft(
                source=source,
                actor=context.acting(),
                version=version,
                system_model=system_model,
                replace=replace,
                accept_terms=accept_terms,
                package=package,
                name=name,
                drop_unlinked=drop_unlinked,
            )
        )
        pid = await asyncio.to_thread(context.installer.start, posted.id, account)
        started = await context.installs.update_install(posted.id, InstallPatch(pid=pid))
        context.keep_watching(
            watch_install(context.events, context.installs, context.installer, posted.id)
        )
        return Answer[Install](value=started, view_url=databases_link(context))


async def list_installs(context: ServerContext) -> Answer[list[Install]]:
    """Every install, newest first, each settled when its process is gone."""
    found = await context.installs.list_installs()
    return Answer[list[Install]](
        value=[
            await reap_install(context.installs, context.installer, install) for install in found
        ],
        view_url=databases_link(context),
    )


async def get_install(context: ServerContext, install_id: str) -> Answer[Install]:
    """One install: its status, the step it is on with that step's count, the summary on success,
    the terms when it stopped at them, or the failure."""
    install = await context.installs.get_install(as_uuid(install_id))
    return Answer[Install](
        value=await reap_install(context.installs, context.installer, install),
        view_url=databases_link(context),
    )


async def cancel_install(context: ServerContext, install_id: str) -> Answer[Install]:
    """Ask an install to stop. It stops at the next step boundary and at each progress report, and
    leaves the database as it was. An install already finished is refused; post it again
    instead."""
    install = await context.installs.cancel_install(as_uuid(install_id))
    return Answer[Install](value=install, view_url=databases_link(context))


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the five install tools, in roster order."""
    server.tool(
        name="list_sources",
        annotations=READ,
        description=(
            "Every source a background database installs from, with the versions its profiles "
            "pin, the system models it holds, whether it has terms to accept, and whether this "
            "server holds the account its install needs. install_database posts one of them."
        ),
    )(boundary(bound(list_sources, context)))
    server.tool(
        name="install_database",
        annotations=WRITE,
        description=(
            "Install a background database from a source, in a process of this server's own, and "
            "answer the install. Show the person the terms of a source that has them and pass "
            "accept_terms only on their word; the record names who accepted. An openlca install "
            "takes the zip the person holds as package, with name and version. A source whose "
            "account is not held is refused with what to set, and a credential is entered by the "
            "person on the page: never ask them for a password here. list_installs and "
            "get_install follow the install, cancel_install asks it to stop."
        ),
    )(boundary(bound(install_database, context)))
    server.tool(
        name="list_installs",
        annotations=READ,
        description=(
            "Every install, newest first, with the step each is on, the summary of one that "
            "finished, the terms one stopped at and the failure of one that failed. An install "
            "whose process is gone answers as failed."
        ),
    )(boundary(bound(list_installs, context)))
    server.tool(
        name="get_install",
        annotations=READ,
        description=(
            "One install by its id: its status, the step it is on with that step's count, its "
            "summary once it is done, and the failure of one whose process is gone."
        ),
    )(boundary(bound(get_install, context)))
    server.tool(
        name="cancel_install",
        annotations=WRITE,
        description=(
            "Ask an install to stop. It stops between steps and keeps the database as it was, "
            "since the write replaces the database's directory only once it is whole. An install "
            "already finished is refused, and one that stopped is posted again rather than "
            "resumed."
        ),
    )(boundary(bound(cancel_install, context)))
