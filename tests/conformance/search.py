"""The search port's contract: membership, filters, paging and counts, never ranking."""

from __future__ import annotations

import pytest

from ecosemantic.errors import Invalid
from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS

UNDER_24 = [
    "ISIC rev.4 ecoinvent: 24:Manufacture of basic metals",
    "ISIC rev.4 ecoinvent: 2410:Manufacture of basic iron and steel",
    "ISIC rev.4 ecoinvent: 2420:Manufacture of basic precious and other non-ferrous metals",
]
BASIC_METALS = ["aluminium production", "copper production", "steel production"]


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

    @pytest.mark.parametrize("query", ["", '""', "*"])
    async def test_a_query_with_no_term_is_invalid(self, search, query: str) -> None:
        for call in (search.processes, search.elementary_flows, search.methods):
            with pytest.raises(Invalid, match="a search needs at least one term"):
                await call(FIXTURE_DB, query)

    async def test_a_limit_below_one_is_invalid(self, search) -> None:
        for call in (search.processes, search.elementary_flows, search.methods):
            with pytest.raises(Invalid, match="limit is at least 1"):
                await call(FIXTURE_DB, "steel", limit=0)

    async def test_a_flow_query_matches_its_compartment(self, search) -> None:
        hits = await search.elementary_flows(FIXTURE_DB, "air")
        assert {h.ref.id for h in hits.items} == {FLOW_IDS[k] for k in ("co2", "ch4", "pm")}

    async def test_a_prefix_term_matches_a_longer_word(self, search) -> None:
        hits = await search.processes(FIXTURE_DB, "ste*")
        assert CODES["steel"] in {h.ref.id for h in hits.items}

    async def test_a_quoted_term_matches_as_its_words(self, search) -> None:
        hits = await search.processes(FIXTURE_DB, '"steel production"')
        assert CODES["steel"] in {h.ref.id for h in hits.items}

    async def test_browse_processes_by_classification(self, search) -> None:
        page = await search.processes(FIXTURE_DB, "", classifications=UNDER_24)
        assert [h.name for h in page.items] == BASIC_METALS
        assert [h.relevance for h in page.items] == [0.0, 0.0, 0.0]

    async def test_a_filter_narrows_a_classification(self, search) -> None:
        page = await search.processes(FIXTURE_DB, "steel", classifications=UNDER_24)
        assert [h.name for h in page.items] == ["steel production"]

    async def test_a_query_of_no_term_under_a_classification_lists_it_all(self, search) -> None:
        page = await search.processes(FIXTURE_DB, "*", classifications=UNDER_24)
        assert [h.name for h in page.items] == BASIC_METALS

    async def test_browsing_pages(self, search) -> None:
        first = await search.processes(FIXTURE_DB, "", classifications=UNDER_24, limit=2)
        assert [h.name for h in first.items] == BASIC_METALS[:2]
        assert first.has_more and first.next_cursor is not None
        rest = await search.processes(
            FIXTURE_DB, "", classifications=UNDER_24, limit=2, cursor=first.next_cursor
        )
        assert [h.name for h in rest.items] == BASIC_METALS[2:]
        assert not rest.has_more and rest.next_cursor is None

    async def test_browse_flows_by_compartment(self, search) -> None:
        page = await search.elementary_flows(FIXTURE_DB, "", compartment="air")
        assert [h.name for h in page.items] == [
            "Carbon dioxide, fossil",
            "Methane, fossil",
            "Particulate matter",
        ]
        sub = await search.elementary_flows(
            FIXTURE_DB, "", sub_compartment="urban air close to ground"
        )
        assert [h.name for h in sub.items] == ["Particulate matter"]

    async def test_a_filter_that_is_no_browsing_filter_does_not_permit_a_query_of_no_term(
        self, search
    ) -> None:
        with pytest.raises(Invalid, match="a search needs at least one term"):
            await search.processes(FIXTURE_DB, "", unit="kilogram")
        with pytest.raises(Invalid, match="a search needs at least one term"):
            await search.elementary_flows(FIXTURE_DB, "", flow_type="emission")
