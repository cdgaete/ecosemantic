from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from ecosemantic.mcp.calls import InProgress, begin, end
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.direct import run_tool
from ecosemantic.model.entities import Actor, Person, ProductSystem, method_id
from tests.fixture_data import GWP

ANA = Person(id="a", name="Ana")
GWP_ID = method_id(" > ".join(GWP))


def test_a_copy_for_a_person_shares_the_store(context: ServerContext) -> None:
    copy = context.for_person(ANA)
    assert copy.locks is context.locks
    assert copy.events is context.events
    assert copy.watchers is context.watchers
    assert copy.storage is context.storage
    assert copy.client == {} and copy.client is not context.client


def test_an_agent_s_write_names_the_agent_and_the_person(context: ServerContext) -> None:
    page = context.for_person(ANA)
    call = InProgress(context=page, agent="claude", client="Claude", origin="agent")
    token = begin(call)
    try:
        acting = page.acting()
    finally:
        end(token)
    assert acting == Actor(kind="agent", id="claude", name="Claude", on_behalf_of=ANA)


def test_the_page_s_write_names_the_person(context: ServerContext) -> None:
    page = context.for_person(ANA)
    call = InProgress(context=page, agent="view", client="view", origin="view")
    token = begin(call)
    try:
        in_a_call = page.acting()
    finally:
        end(token)
    assert in_a_call == Actor(kind="person", id="a", name="Ana")
    assert page.acting() == Actor(kind="person", id="a", name="Ana")


def test_without_a_person_every_writer_is_as_before(context: ServerContext) -> None:
    call = InProgress(context=context, agent="claude", client="Claude", origin="agent")
    token = begin(call)
    try:
        through_mcp = context.acting()
    finally:
        end(token)
    call = InProgress(context=context, agent="view", client="view", origin="view")
    token = begin(call)
    try:
        through_the_page = context.acting()
    finally:
        end(token)
    assert through_mcp == Actor(kind="agent", id="claude", name="Claude")
    assert through_the_page == Actor(kind="agent", id="view", name="view")
    assert context.posted_by("Mallory") == Actor(kind="person", name="Mallory")
    assert context.acting() == context.actor


async def test_a_recorded_call_names_the_person(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    before = {call.id for call in await context.activity.list_calls()}
    await run_tool(
        full_server,
        context.for_person(ANA),
        "calculate_impact",
        {"product_system_id": str(fixture_system_stored.id), "method_id": GWP_ID},
        started=True,
    )
    (call,) = [call for call in await context.activity.list_calls() if call.id not in before]
    assert call.person == ANA


async def test_a_context_serves_its_own_store(
    ports_only: ServerContext, product_system: ProductSystem
) -> None:
    queue = ports_only.events.subscribe_all()
    async with ports_only.serving():
        await ports_only.storage.put_product_system(product_system, ports_only.actor, "created")
        published = await asyncio.wait_for(queue.get(), 5)
    ports_only.events.unsubscribe_all(queue)
    assert published.kind == "entry"
    assert published.product_system_id == product_system.id
