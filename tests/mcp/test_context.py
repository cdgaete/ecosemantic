from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ecosemantic.local import build_context
from ecosemantic.mcp.calls import InProgress, begin, end
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import Actor, Person
from ecosemantic.ports.calculation import CalculationPort
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.resolver import Resolver
from ecosemantic.ports.run import RunPort
from ecosemantic.ports.search import SearchPort
from ecosemantic.ports.storage import StoragePort
from tests.fixture_data import FIXTURE_DB


def test_context_binds_every_port(context: ServerContext) -> None:
    assert isinstance(context.inventory, InventoryPort)
    assert isinstance(context.search, SearchPort)
    assert isinstance(context.calculation, CalculationPort)
    assert isinstance(context.storage, StoragePort)
    assert isinstance(context.resolver, Resolver)
    assert isinstance(context.runs, RunPort)
    assert context.actor.kind == "agent"


async def test_the_store_serves_the_fixture_database(context: ServerContext) -> None:
    assert FIXTURE_DB in {d.name for d in await context.inventory.list_databases()}


def test_a_missing_directory_names_itself(bundle_dir: Path, tmp_path: Path) -> None:
    missing = tmp_path / "not-there"
    with pytest.raises(FileNotFoundError, match="not-there"):
        build_context(bundle_dir, missing)
    with pytest.raises(FileNotFoundError, match="no-data"):
        build_context(tmp_path / "no-data", tmp_path)


async def test_closing_stops_the_watchers_it_holds(bundle_dir: Path, tmp_path: Path) -> None:
    built = build_context(bundle_dir, tmp_path)
    built.keep_watching(asyncio.sleep(60))
    (watcher,) = built.watchers
    built.close()
    await asyncio.gather(watcher, return_exceptions=True)
    assert watcher.cancelled() and built.watchers == set()


def test_outside_a_call_the_context_acts_as_its_own_actor(context: ServerContext) -> None:
    assert context.acting() == context.actor


def test_inside_a_call_the_context_acts_as_the_agent(context: ServerContext) -> None:
    call = InProgress(context=context, agent="electricity", client="claude-code", origin="agent")
    token = begin(call)
    try:
        assert context.acting() == Actor(kind="agent", id="electricity", name="claude-code")
    finally:
        end(token)


def test_a_page_call_places_as_a_person_with_and_without_one_signed_in(
    context: ServerContext,
) -> None:
    person = Person(id="a", name="Ana")
    call = InProgress(context=context, agent="view", client="view", origin="view")
    token = begin(call)
    try:
        anonymous = context.placing()
        signed_in = context.for_person(person).placing()
    finally:
        end(token)
    assert (anonymous, signed_in) == ("person", "person")


def test_an_agent_call_places_as_an_agent_with_and_without_a_person(
    context: ServerContext,
) -> None:
    person = Person(id="a", name="Ana")
    call = InProgress(context=context, agent="claude", client="Claude", origin="agent")
    token = begin(call)
    try:
        anonymous = context.placing()
        signed_in = context.for_person(person).placing()
    finally:
        end(token)
    assert (anonymous, signed_in) == ("agent", "agent")


def test_outside_a_call_the_context_places_as_its_actor(context: ServerContext) -> None:
    assert context.placing() == context.actor.kind
