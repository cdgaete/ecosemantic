"""The search port's contract: membership, filters, paging and counts, never ranking."""

from __future__ import annotations

from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS


class SearchConformance:
    async def test_membership_and_filters(self, search) -> None:
        hits = await search.processes(FIXTURE_DB, "steel")
        assert CODES["steel"] in {h.ref.id for h in hits.items}
        filtered = await search.processes(FIXTURE_DB, "production", unit="kilowatt hour")
        assert {h.ref.id for h in filtered.items} == {CODES["elec"]}
        assert (await search.processes(FIXTURE_DB, "production", location="CH")).items == []

    async def test_paging_is_complete_and_disjoint(self, search) -> None:
        seen: set[str] = set()
        cursor = None
        while True:
            page = await search.processes(FIXTURE_DB, "production", limit=4, cursor=cursor)
            ids = {h.ref.id for h in page.items}
            assert ids.isdisjoint(seen)
            seen |= ids
            if not page.has_more:
                break
            cursor = page.next_cursor
        assert seen == {CODES[c] for c in CODES if c != "lorry"}

    async def test_flows_and_methods(self, search) -> None:
        elementary_flows = await search.elementary_flows(FIXTURE_DB, "fossil", compartment="air")
        assert {h.ref.id for h in elementary_flows.items} == {FLOW_IDS["co2"], FLOW_IDS["ch4"]}
        methods = await search.methods(FIXTURE_DB, "climate")
        assert [m.spec for m in methods.items] == ["fixture > gwp > climate change > GWP100"]

    async def test_method_paging_says_there_is_more_and_its_cursor_reaches_the_rest(
        self, search
    ) -> None:
        # the fixture carries two methods, both under "fixture"
        first = await search.methods(FIXTURE_DB, "fixture", limit=1)
        assert len(first.items) == 1 and first.has_more and first.next_cursor is not None
        rest = await search.methods(FIXTURE_DB, "fixture", limit=1, cursor=first.next_cursor)
        assert len(rest.items) == 1 and not rest.has_more
        assert {m.id for m in first.items} | {m.id for m in rest.items} == {
            m.id for m in (await search.methods(FIXTURE_DB, "fixture", limit=5)).items
        }
