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

from ecosemantic.mcp.accounts import account_advice
from ecosemantic.mcp.context import AccountStart, ServerContext, Start
from ecosemantic.mcp.server import build_server
from ecosemantic.ports.types import Account, DatabaseSource, InstallPatch
from tests.mcp.test_accounts import SCREEN, TRAY, source
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
            system_models=["cutoff"],
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
            {"source": "ecoinvent", "version": "3.11", "system_model": "cutoff"},
        )
        install = value(answered)
        one = value(await client.call_tool("get_install", {"install_id": install["id"]}))
        every = value(await client.call_tool("list_installs", {}))
    assert install["draft"]["source"] == "ecoinvent"
    assert install["draft"]["version"] == "3.11" and install["draft"]["system_model"] == "cutoff"
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
                {"source": "ecoinvent", "version": "3.11", "system_model": "cutoff"},
            )
        )
        await installs.update_install(uuid.UUID(first["id"]), InstallPatch(status="done"))
        second = value(await client.call_tool("install_database", {"source": "uslci"}))
    handed = dict(launcher.started)
    account = handed[uuid.UUID(first["id"])]
    assert account is not None and account.username == "me"
    assert account.password.get_secret_value() == "hunter2"
    assert handed[uuid.UUID(second["id"])] is None


async def test_list_sources_hints_the_advice_for_accounts_not_held(held: Held) -> None:
    over, _installs, _launcher = held
    entry = AccountStart(start="tray", screen=SCREEN)
    without = dataclasses.replace(over, credentials={}, accounts=entry)
    held_every = dataclasses.replace(without, credentials={"nexus": ACCOUNT, "ecoinvent": ACCOUNT})
    only_bafu = dataclasses.replace(without, credentials={"ecoinvent": ACCOUNT})
    async with Client(build_server(without)) as client:
        unheld = (await client.call_tool("list_sources", {})).structured_content
    async with Client(build_server(held_every)) as client:
        every = (await client.call_tool("list_sources", {})).structured_content
    async with Client(build_server(only_bafu)) as client:
        one = (await client.call_tool("list_sources", {})).structured_content
    hint = unheld["hint"]
    assert "bafu" in hint and "ecoinvent" in hint
    assert TRAY in hint
    assert one["hint"].startswith("bafu needs a Nexus account, which this engine does not hold.")
    assert "ecoinvent needs" not in one["hint"]
    assert every["hint"] is None


async def test_a_source_names_its_account_as_the_page_shows_it(held: Held) -> None:
    over, _installs, _launcher = held
    without = dataclasses.replace(
        over, credentials={}, accounts=AccountStart(start="tray", screen=SCREEN)
    )
    async with Client(build_server(without)) as client:
        answered = (await client.call_tool("list_sources", {})).structured_content
    listed = {source["name"]: source for source in answered["value"]}
    assert listed["bafu"]["account"] == {"name": "Nexus", "phrase": "a Nexus account"}
    assert listed["ecoinvent"]["account"] == {
        "name": "ecoinvent",
        "phrase": "an ecoinvent account",
    }
    assert listed["openlca"]["account"] is None and listed["uslci"]["account"] is None
    assert "bafu needs a Nexus account" in answered["hint"]
    assert "ecoinvent needs an ecoinvent account" in answered["hint"]


@pytest.mark.parametrize(
    ("start", "screen"),
    [("tray", None), ("terminal", SCREEN), ("headless", None)],
)
async def test_install_database_refuses_with_the_advice_of_the_start(
    held: Held, start: Start, screen: str | None
) -> None:
    over, _installs, launcher = held
    entry = AccountStart(start=start, screen=screen)
    without = dataclasses.replace(over, credentials={}, accounts=entry)
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "bafu"})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "unavailable"
    hint = refused["details"]["hint"]
    assert hint == account_advice(entry, needed=[source("bafu", "nexus")]).said()
    assert "/databases" not in hint
    assert launcher.started == []


async def test_a_version_the_source_does_not_offer_is_refused_before_the_account_is_asked(
    held: Held,
) -> None:
    over, installs, launcher = held
    without = dataclasses.replace(over, credentials={})
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "install_database",
                {"source": "ecoinvent", "version": "9.9", "system_model": "cutoff"},
            )
    refused = json.loads(str(caught.value))
    assert refused["error"] == "invalid"
    assert refused["message"] == "ecoinvent offers no version '9.9'; it offers 3.11"
    assert await installs.list_installs() == [] and launcher.started == []


async def test_a_system_model_the_source_does_not_offer_is_refused_before_the_account_is_asked(
    held: Held,
) -> None:
    over, installs, launcher = held
    without = dataclasses.replace(over, credentials={})
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "install_database",
                {"source": "ecoinvent", "version": "3.11", "system_model": "consequential"},
            )
    refused = json.loads(str(caught.value))
    assert refused["error"] == "invalid"
    assert refused["message"] == (
        "ecoinvent offers no system model 'consequential'; it offers cutoff"
    )
    assert await installs.list_installs() == [] and launcher.started == []


async def test_a_draft_that_lacks_what_its_source_needs_is_refused_before_the_account_is_asked(
    held: Held,
) -> None:
    over, installs, launcher = held
    without = dataclasses.replace(over, credentials={})
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "ecoinvent"})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "invalid"
    assert refused["message"] == "an ecoinvent draft needs a version and a system model"
    assert await installs.list_installs() == [] and launcher.started == []


async def test_a_version_and_system_model_the_source_offers_still_asks_for_the_account(
    held: Held,
) -> None:
    over, installs, launcher = held
    entry = AccountStart(start="tray", screen=SCREEN)
    without = dataclasses.replace(over, credentials={}, accounts=entry)
    async with Client(build_server(without)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "install_database",
                {"source": "ecoinvent", "version": "3.11", "system_model": "cutoff"},
            )
    refused = json.loads(str(caught.value))
    assert refused["error"] == "unavailable"
    assert refused["message"] == "ecoinvent installs from an account this server does not hold"
    assert (
        refused["details"]["hint"]
        == account_advice(entry, needed=[source("ecoinvent", "ecoinvent")]).said()
    )
    assert await installs.list_installs() == [] and launcher.started == []


async def test_a_source_this_server_does_not_offer_is_not_found_naming_list_sources(
    held: Held,
) -> None:
    over, _installs, _launcher = held
    offered = [found for found in sources() if found.name != "bafu"]
    narrowed = dataclasses.replace(over, installer=MemoryInstaller(offered))
    async with Client(build_server(narrowed)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "bafu"})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "not_found"
    assert "bafu" in refused["message"] and "list_sources" in refused["message"]


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


async def test_a_served_database_is_refused_before_anything_starts_unless_replaced(
    held: Held,
) -> None:
    over, installs, launcher = held
    served = (await over.inventory.list_databases())[0].name
    launcher.names["ecoinvent"] = served
    draft = {"source": "ecoinvent", "version": "3.11", "system_model": "cutoff"}
    async with Client(build_server(over)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", draft)
        refused = json.loads(str(caught.value))
        assert await installs.list_installs() == [] and launcher.started == []
        replaced = value(await client.call_tool("install_database", {**draft, "replace": True}))
    assert refused["error"] == "conflict"
    assert refused["message"] == (
        f"database {served!r} is installed; pass replace to install it again"
    )
    assert replaced["draft"]["replace"] is True and len(launcher.started) == 1


async def test_drop_unlinked_is_refused_for_a_source_that_cuts_off_what_its_release_lists(
    held: Held,
) -> None:
    over, installs, launcher = held
    async with Client(build_server(over)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("install_database", {"source": "uslci", "drop_unlinked": True})
    refused = json.loads(str(caught.value))
    assert refused["error"] == "invalid"
    assert "drop_unlinked applies to an openlca install" in refused["message"]
    assert await installs.list_installs() == [] and launcher.started == []


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
