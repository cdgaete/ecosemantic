"""The calculation port's contract over the fixture background and product system: the exact
results, and Monte Carlo. Subclass with a `calculation`."""

from __future__ import annotations

import pytest

from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import BackgroundRef, ForegroundRef
from ecosemantic.ports.types import MonteCarloConfig, System
from tests.fixture_data import CODES, FIXTURE_DB

# the fixture's method as its bundle keys it: the category and the indicator in one name
GWP_METHOD = Method.of(("fixture", "gwp", "climate change > GWP100"), "kg CO2-Eq")
WIDGET = [DemandItem(ref=ForegroundRef(code="widget"), amount=1.0)]


class CalculationConformance:
    async def test_scores(self, calculation, fixture_system: System) -> None:
        score = await calculation.score(fixture_system, WIDGET, GWP_METHOD)
        assert score.value == pytest.approx(4.158)
        background = System(database=FIXTURE_DB)
        steel = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)]
        assert (await calculation.score(background, steel, GWP_METHOD)).value == pytest.approx(2.78)

    async def test_hotspots_and_tree_agree_with_the_score(
        self, calculation, fixture_system: System
    ) -> None:
        hotspots = await calculation.hotspots(fixture_system, WIDGET, GWP_METHOD, top_n=20)
        assert sum(h.score for h in hotspots.items) == pytest.approx(4.158)
        tree = await calculation.contribution_tree(
            fixture_system, WIDGET, GWP_METHOD, max_level=4, max_nodes=200, cutoff=0.0
        )
        assert tree.root.score == pytest.approx(4.158) and not tree.truncated

    async def test_flow_hotspots_partition_the_score(
        self, calculation, fixture_system: System
    ) -> None:
        found = await calculation.flow_hotspots(fixture_system, WIDGET, GWP_METHOD, top_n=20)
        assert found.total.value == pytest.approx(4.158)
        assert sum(f.score for f in found.items) == pytest.approx(4.158)
        assert [f.name for f in found.items] == ["Carbon dioxide, fossil", "Methane, fossil"]
        assert found.items[0].amount == pytest.approx(3.85) and found.items[0].rank == 1

    async def test_inventory_rows(self, calculation, fixture_system: System) -> None:
        found = await calculation.inventory(fixture_system, WIDGET)
        co2 = sum(r.amount for r in found.rows if r.name == "Carbon dioxide, fossil")
        assert co2 == pytest.approx(3.85)
        assert found.dropped == 0 and found.floor == pytest.approx(1e-34 * 3.85)


class MonteCarloConformance:
    async def test_monte_carlo_is_reproducible(self, calculation, fixture_system: System) -> None:
        config = MonteCarloConfig(n=5, seed=3)
        first = await calculation.monte_carlo(fixture_system, WIDGET, [GWP_METHOD], config)
        second = await calculation.monte_carlo(fixture_system, WIDGET, [GWP_METHOD], config)
        assert first.categories[0].samples == second.categories[0].samples and first.n == 5
