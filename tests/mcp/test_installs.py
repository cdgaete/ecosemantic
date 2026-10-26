from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.ports.types import Account, DatabaseSource, InstallPatch
from tests.memory_installs import MemoryInstaller, MemoryInstalls

VIEW = "http://127.0.0.1:8000/?token=abc"
PAGE = "http://127.0.0.1:8000/databases?token=abc"
ACCOUNT = Account(username="me", password=SecretStr("hunter2"))


def sources() -> list[DatabaseSource]:
    """The four sources as the launcher answers them: the versions, what each needs, the terms."""
    return [
        DatabaseSource(
            name="openlca",
            versions=[],
            system_models=["unit process"],
            credential=None,
            terms=False,
        ),
        DatabaseSource(
            name="uslci", versions=["2024"], system_models=[], credential=None, terms=False
        ),
        DatabaseSource(
            name="bafu", versions=["2.2"], system_models=[], credential="nexus", terms=True
        ),
        DatabaseSource(
            name="ecoinvent",
            versions=["3.11"],
            system_models=["cut-off"],
            credential="ecoinvent",
            terms=False,
        ),
    ]


Held = tuple[ServerContext, MemoryInstalls, MemoryInstaller]


@pytest.fixture
async def held(context: ServerContext) -> AsyncIterator[Held]:
    """The fixture's context over the install doubles, holding an ecoinvent account, with the
    page's address announced."""
    installs = MemoryInstalls()
    installer = MemoryInstaller(sources())
    over = dataclasses.replace(
        context,
        installs=installs,
        installer=installer,
        credentials={"ecoinvent": ACCOUNT},
        view_url=VIEW,
        watchers=set(),
    )
    yield over, installs, installer
    for task in over.watchers:
        task.cancel()
    await asyncio.gather(*over.watchers, return_exceptions=True)


def value(out: Any) -> dict[str, Any]:
    """What a tool answered, as its structured content holds it."""
    return out.structured_content["value"]


async def test_install_database_posts_starts_and_answers_the_install(held: Held) -> None:
    over, installs, launcher = held
    async with Client(build_server(over)) as client:
        answered = await client.call_tool(
            "install_database",
            {"source": "ecoinvent", "version": "3.11", "system_model": "cut-off"},
        )
        install = value(answered)
        one = value(await client.call_tool("get_install", {"install_id": install["id"]}))
        every = value(await client.call_tool("list_installs", {}))
    assert install["draft"]["source"] == "ecoinvent"
    assert install["draft"]["version"] == "3.11" and install["draft"]["system_model"] == "cut-off"
    assert install["draft"]["actor"]["kind"] == "agent"
    assert install["status"] == "queued" and install["pid"] == 4242
    assert answered.structured_content["view_url"] == PAGE
    assert one["id"] == install["id"]
    assert [stored["id"] for stored in every] == [install["id"]]
    assert [install_id for install_id, _account in launcher.started] == [uuid.UUID(install["id"])]
    assert (await installs.get_install(uuid.UUID(install["id"]))).pid == 4242


async def test_the_started_process_receives_the_held_account(held: Held) -> None:
    over, installs, launcher = held
    async with Client(build_server(over)) as client:
        first = value(
            await client.call_tool(
                "install_database",
                {"source": "ecoinvent", "version": "3.11", "system_model": "cut-off"},
            )
        )
        await installs.update_install(uuid.UUID(first["id"]), InstallPatch(status="done"))
        second = value(await client.call_tool("install_database", {"source": "uslci"}))
    handed = dict(launcher.started)
    account = handed[uuid.UUID(first["id"])]
    assert account is not None and account.username == "me"
    assert account.password.get_secret_value() == "hunter2"
    assert handed[uuid.UUID(second["id"])] is None


async def test_a_source_whose_account_is_not_held_is_refused_naming_the_page(held: Held) -> None:
    over, _installs, launcher = held
    without = dataclasses.replace(over, credentials={})
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "bafu"})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "unavailable"
    assert refused["details"]["hint"] == (
        "set NEXUS_USERNAME and NEXUS_PASSWORD, or enter the account on the page's Databases "
        f"editor: {PAGE}"
    )
    assert launcher.started == []


async def test_a_second_install_while_one_is_open_is_a_conflict_naming_it(held: Held) -> None:
    over, _installs, launcher = held
    async with Client(build_server(over)) as client:
        first = value(await client.call_tool("install_database", {"source": "uslci"}))
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "uslci"})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "conflict"
    assert refused["message"] == f"install {first['id']} is still queued"
    assert len(launcher.started) == 1


async def test_list_sources_says_which_accounts_are_held_and_never_answers_one(held: Held) -> None:
    over, _installs, _launcher = held
    async with Client(build_server(over)) as client:
        answered = await client.call_tool("list_sources", {})
    listed = {source["name"]: source for source in value(answered)}
    assert set(listed) == {"openlca", "uslci", "bafu", "ecoinvent"}
    assert listed["ecoinvent"]["held"] is True
    assert listed["bafu"]["held"] is False
    assert listed["uslci"]["held"] is True
    assert listed["ecoinvent"]["versions"] == ["3.11"]
    assert listed["bafu"]["terms"] is True
    assert answered.structured_content is not None
    assert "hunter2" not in json.dumps(answered.structured_content)
    assert answered.structured_content["view_url"] == PAGE


async def test_cancel_install_asks_an_open_install_to_stop(held: Held) -> None:
    over, _installs, _launcher = held
    async with Client(build_server(over)) as client:
        posted = value(await client.call_tool("install_database", {"source": "uslci"}))
        cancelling = await client.call_tool("cancel_install", {"install_id": posted["id"]})
        stopped = value(cancelling)
    assert stopped["cancel_requested"] is True and stopped["status"] == "queued"
    assert cancelling.structured_content["view_url"] == PAGE
