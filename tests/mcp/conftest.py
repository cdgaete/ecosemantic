from __future__ import annotations

import uuid

import pytest
from fastmcp import Client, FastMCP

from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import Exchange, ExchangeOverride, ProductSystem, Scenario
from ecosemantic.model.refs import ForegroundRef
from tests.conftest import fixture_system
from tests.fixture_data import FIXTURE_DB


@pytest.fixture
async def bottle(full_server: FastMCP) -> str:
    """The id of a fresh, empty product system on the fixture database."""
    async with Client(full_server) as client:
        out = await client.call_tool(
            "create_product_system", {"name": "bottle", "database": FIXTURE_DB}
        )
    return out.structured_content["value"]["id"]


@pytest.fixture(scope="session")
async def credited_stored(context: ServerContext) -> ProductSystem:
    """The widget with its frame co-producing four widgets, a loop holding a credit, and a
    scenario that makes the frame use two widgets instead."""
    system = fixture_system().product_system
    assert system is not None
    system.id = uuid.uuid5(system.id, "credited")
    system.name = "widget_credited"
    credit = Exchange(
        id=uuid.uuid5(system.id, "credit"),
        type="product",
        name="widget",
        amount=-4.0,
        unit="unit",
        input=ForegroundRef(code="widget"),
    )
    system.process("frame").exchanges.append(credit)
    system.scenarios = [
        Scenario(name="used", overrides=[ExchangeOverride(exchange_id=credit.id, amount=2.0)])
    ]
    system.scenarios[0].base_hash = base_pin(system)
    await context.storage.put_product_system(system, context.actor, "created")
    return system


@pytest.fixture(scope="session")
async def looped_stored(context: ServerContext) -> ProductSystem:
    """The widget with its frame using two widgets, a loop through the functional unit."""
    system = fixture_system().product_system
    assert system is not None
    system.id = uuid.uuid5(system.id, "looped")
    system.name = "widget_looped"
    system.process("frame").exchanges.append(
        Exchange(
            id=uuid.uuid5(system.id, "use"),
            type="product",
            name="widget",
            amount=2.0,
            unit="unit",
            input=ForegroundRef(code="widget"),
        )
    )
    await context.storage.put_product_system(system, context.actor, "created")
    return system
