"""The inventory port's contract over the fixture background. Subclass with an `inventory`."""

from __future__ import annotations

import pytest

from ecosemantic.errors import MethodNotFound, NotFound
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
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
