"""The inventory port's contract over the fixture background. Subclass with an `inventory`."""

from __future__ import annotations

import pytest

from ecosemantic.errors import MethodNotFound, NotFound
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.types import DatabaseSummary, Factor, SubCompartment
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS


class InventoryConformance:
    async def test_missing_names_the_references_a_database_lacks(self, inventory) -> None:
        steel = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])
        absent = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"][:-1] + "0")
        co2 = ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"])
        nowhere = ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"][:-1] + "0")
        assert await inventory.missing([steel, absent, co2, nowhere]) == [absent, nowhere]
        assert await inventory.missing([steel, co2]) == []
        with pytest.raises(NotFound, match="'nowhere'"):
            await inventory.missing([BackgroundRef(database="nowhere", id=CODES["steel"])])

    async def test_treatments_names_none_of_the_fixture_s_producers(self, inventory) -> None:
        steel = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])
        assert await inventory.treatments([steel]) == []
        with pytest.raises(NotFound, match="'nowhere'"):
            await inventory.treatments([BackgroundRef(database="nowhere", id=CODES["steel"])])

    async def test_lists_the_fixture_database(self, inventory) -> None:
        names = {d.name: d for d in await inventory.list_databases()}
        assert (
            names[FIXTURE_DB].elementary_flows == FIXTURE_BIO and names[FIXTURE_DB].scheme == "olca"
        )

    async def test_get_database_by_either_name(self, inventory) -> None:
        by_own_name = await inventory.get_database(FIXTURE_DB)
        by_flows_name = await inventory.get_database(FIXTURE_BIO)
        assert by_own_name == by_flows_name and by_own_name.name == FIXTURE_DB
        with pytest.raises(NotFound, match=repr(FIXTURE_DB)):
            await inventory.get_database("nowhere")

    async def test_activity_with_exchanges(self, inventory) -> None:
        steel = await inventory.get_process(
            BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), exchanges=True
        )
        assert steel.name == "steel production" and steel.unit == "kilogram"
        assert steel.exchanges is not None
        assert [
            (e.type, e.side, e.reference, e.flow, e.supplier, e.cut_off) for e in steel.exchanges
        ] == [
            ("product", "output", True, "steel", None, None),
            ("product", "input", False, "electricity", "electricity production", None),
            ("elementary", "output", False, "Carbon dioxide, fossil", None, None),
            ("elementary", "output", False, "Methane, fossil", None, None),
        ]
        assert [
            (e.input.kind, e.input.id, e.amount) for e in steel.exchanges if e.input is not None
        ] == [
            ("background", CODES["steel"], 1.0),
            ("background", CODES["elec"], 2.0),
            ("elementary_flow", FLOW_IDS["co2"], 0.5),
            ("elementary_flow", FLOW_IDS["ch4"], 0.01),
        ]
        assert steel.classifications == [
            "ISIC rev.4 ecoinvent: 2410:Manufacture of basic iron and steel",
            "EcoSpold01Categories: metals/production",
        ]
        with pytest.raises(NotFound):
            await inventory.get_process(
                BackgroundRef(database=FIXTURE_DB, id=CODES["steel"][:-1] + "0")
            )

    async def test_flow(self, inventory) -> None:
        flow = await inventory.get_elementary_flow(
            ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["water_in"])
        )
        # a bundle files a natural resource under openLCA's "Resource"
        assert (flow.name, flow.compartment, flow.sub_compartment, flow.unit) == (
            "Water, river",
            "Resource",
            "in water",
            "cubic meter",
        )

    async def test_methods_and_suggestions(self, inventory) -> None:
        methods = await inventory.list_methods(FIXTURE_DB)
        assert {m.spec for m in methods} == {
            "fixture > gwp > climate change > GWP100",
            "fixture > water > water use > m3",
        }
        gwp = next(m for m in methods if m.impact_method == "gwp")
        assert await inventory.resolve_method(FIXTURE_DB, gwp.id) == gwp
        with pytest.raises(MethodNotFound) as caught:
            await inventory.resolve_method(FIXTURE_DB, "fixture > gwp > Climate Change > GWP 100")
        assert gwp in caught.value.suggestions

    async def test_units_locations_compartments(self, inventory) -> None:
        assert await inventory.list_units(FIXTURE_DB) == [
            "kilogram",
            "kilowatt hour",
            "ton kilometer",
        ]
        assert await inventory.list_locations(FIXTURE_DB) == ["GLO"]
        compartments = await inventory.list_compartments(FIXTURE_DB)
        assert {c.name: c.flow_count for c in compartments} == {"air": 3, "Resource": 1}
        found = {c.name: c.sub_compartments for c in compartments}
        # co2, ch4 and pm are all in air; pm alone is in its sub-compartment
        assert found["air"] == [SubCompartment(name="urban air close to ground", flow_count=1)]
        assert found["Resource"] == [SubCompartment(name="in water", flow_count=1)]

    async def test_summarize(self, inventory) -> None:
        assert await inventory.summarize(FIXTURE_DB) == DatabaseSummary(
            processes=12, elementary_flows=4, indicators=2, units=3, locations=1
        )

    async def test_classification_schemes(self, inventory) -> None:
        schemes = await inventory.list_classifications(FIXTURE_DB)
        assert [
            (scheme.scheme, scheme.processes, scheme.values)
            for scheme in sorted(schemes, key=lambda found: found.scheme)
        ] == [
            ("By-product classification", 2, 1),
            ("CPC", 2, 2),
            ("EcoSpold01Categories", 4, 3),
            ("ISIC rev.4 ecoinvent", 4, 4),
        ]

    async def test_classification_values(self, inventory) -> None:
        values = await inventory.classification_values(FIXTURE_DB, "EcoSpold01Categories")
        assert [
            (value.value, value.processes)
            for value in sorted(values, key=lambda found: found.value)
        ] == [
            ("EcoSpold01Categories: metals/extraction", 1),
            ("EcoSpold01Categories: metals/production", 2),
            ("EcoSpold01Categories: transport systems/road", 1),
        ]

    async def test_factors(self, inventory) -> None:
        assert (await inventory.factors(FIXTURE_DB, "m_bff077f3bd")).items == [
            Factor(
                flow=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"]),
                name="Carbon dioxide, fossil",
                compartment="air",
                sub_compartment=None,
                unit="kilogram",
                factor=1.0,
            ),
            Factor(
                flow=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["ch4"]),
                name="Methane, fossil",
                compartment="air",
                sub_compartment=None,
                unit="kilogram",
                factor=28.0,
            ),
        ]
        methane = await inventory.factors(FIXTURE_DB, "m_bff077f3bd", query="methane")
        assert [factor.name for factor in methane.items] == ["Methane, fossil"]
        both = await inventory.factors(FIXTURE_DB, "m_bff077f3bd", query="AIR fossil")
        assert [factor.name for factor in both.items] == [
            "Carbon dioxide, fossil",
            "Methane, fossil",
        ]

    async def test_factors_page(self, inventory) -> None:
        first = await inventory.factors(FIXTURE_DB, "m_bff077f3bd", limit=1)
        assert [factor.name for factor in first.items] == ["Carbon dioxide, fossil"]
        assert first.has_more and first.next_cursor is not None
        second = await inventory.factors(
            FIXTURE_DB, "m_bff077f3bd", limit=1, cursor=first.next_cursor
        )
        assert [factor.name for factor in second.items] == ["Methane, fossil"]
        assert not second.has_more and second.next_cursor is None

    async def test_factors_of_an_unknown_method(self, inventory) -> None:
        with pytest.raises(NotFound, match="m_0000000000"):
            await inventory.factors(FIXTURE_DB, "m_0000000000")
        with pytest.raises(NotFound, match="'nope'"):
            await inventory.factors("nope", "m_bff077f3bd")

    async def test_an_unknown_scheme_is_not_found(self, inventory) -> None:
        with pytest.raises(NotFound, match="NACE"):
            await inventory.classification_values(FIXTURE_DB, "NACE")

    async def test_an_unserved_database_is_not_found(self, inventory) -> None:
        with pytest.raises(NotFound, match="'nope'"):
            await inventory.summarize("nope")
        with pytest.raises(NotFound, match="'nope'"):
            await inventory.list_classifications("nope")
        with pytest.raises(NotFound, match="'nope'"):
            await inventory.classification_values("nope", "CPC")
