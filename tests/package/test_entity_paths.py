"""An id from an installed database names an entity's file and no path."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from ecosemantic.backends.native.install import install
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import envelope_of
from ecosemantic.mcp.server import build_server
from ecosemantic.package.background import read_background
from tests.engine_fixture import fixture_bundle
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DB, FLOW_IDS

ESCAPING = "../../../../escaped"


@pytest.fixture
def crafted(tmp_path: Path) -> Iterator[ServerContext]:
    """An engine whose installed database came from a zip that gives one flow a path for an id."""
    written = fixture_bundle(tmp_path)
    named = next(iter(FLOW_IDS.values()))
    zipped = tmp_path / "crafted.zip"
    with zipfile.ZipFile(written) as read, zipfile.ZipFile(zipped, "w") as out:
        for member in read.namelist():
            out.writestr(member, read.read(member).replace(named.encode(), ESCAPING.encode()))
    (tmp_path / "data").mkdir()
    (tmp_path / "held" / "systems").mkdir(parents=True)
    background = read_background(zipped, FIXTURE_DB, foreground=frozenset())
    install(tmp_path / "data", background, zipped, version="1", system_model="unit process")
    built = build_context(tmp_path / "data", tmp_path / "held" / "systems", environ={})
    yield built
    built.close()


async def test_an_id_that_is_a_path_writes_no_file_outside_its_package(
    crafted: ServerContext, tmp_path: Path
) -> None:
    async with Client(build_server(crafted)) as client:
        created = await client.call_tool(
            "create_product_system", {"name": "cup", "database": FIXTURE_DB}
        )
        system_id = created.structured_content["value"]["id"]
        process = {"code": "cup", "name": "cup", "unit": "kilogram", "reference_product": "cup"}
        await client.call_tool("create_process", {"product_system_id": system_id, **process})
        held = crafted.systems_dir / system_id
        before = {path: path.read_bytes() for path in held.rglob("*") if path.is_file()}
        with pytest.raises(ToolError) as refused:
            await client.call_tool(
                "create_exchange",
                {
                    "product_system_id": system_id,
                    "code": "cup",
                    "type": "elementary",
                    "amount": 1,
                    "input": {"kind": "elementary_flow", "database": FIXTURE_BIO, "id": ESCAPING},
                },
            )
    assert envelope_of(refused.value).error == "invalid"
    assert list(tmp_path.rglob("escaped*")) == []
    assert {path: path.read_bytes() for path in held.rglob("*") if path.is_file()} == before
