from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from ecosemantic.model.entities import ProductSystem, method_id
from ecosemantic.package.package import read_package, unzip_package
from tests.fixture_data import GWP

GWP_ID = method_id(" > ".join(GWP))


async def _validates_calculates_draws_and_exports(
    server: FastMCP, system: ProductSystem, score: float, tmp_path: Path
) -> None:
    async with Client(server) as client:
        report = await client.call_tool(
            "validate_product_system", {"product_system_id": str(system.id)}
        )
        impact = await client.call_tool(
            "calculate_impact", {"product_system_id": str(system.id), "method_id": GWP_ID}
        )
        layout = await client.call_tool("graph_layout", {"product_system_id": str(system.id)})
        await client.call_tool(
            "export_product_system",
            {"product_system_id": str(system.id), "path": str(tmp_path / "out.zip")},
        )
    assert report.structured_content["value"]["is_valid"]
    assert impact.structured_content["value"]["scores"][0]["value"] == pytest.approx(score)
    assert len({card["x"] for card in layout.structured_content["value"]["cards"]}) > 1
    unzip_package(tmp_path / "out.zip", tmp_path / "back")
    assert read_package(tmp_path / "back")[0].reference_process == "widget"


async def test_a_functional_unit_inside_a_loop_validates_calculates_draws_and_exports(
    full_server: FastMCP, looped_stored: ProductSystem, tmp_path: Path
) -> None:
    # the widget scores 4.158; a frame using two widgets doubles its output, 4.158 / (1 - 0.5)
    await _validates_calculates_draws_and_exports(full_server, looped_stored, 8.316, tmp_path)


async def test_a_functional_unit_inside_a_credit_loop_validates_calculates_draws_and_exports(
    full_server: FastMCP, credited_stored: ProductSystem, tmp_path: Path
) -> None:
    # a frame crediting four widgets halves the widget's output, 4.158 / (1 + 1)
    await _validates_calculates_draws_and_exports(full_server, credited_stored, 2.079, tmp_path)
