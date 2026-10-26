from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.exceptions import ToolError

from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Case, Parameter, ProductSystem, method_id
from ecosemantic.model.refs import SystemRef
from tests.conftest import frame_system, uid, widget_linking
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS, GWP
from tests.mcp.test_runs import finished, starting

GWP_ID = method_id(" > ".join(GWP))


async def _created(client: Client, name: str, *codes: str) -> str:
    """A system on the fixture database with a unit process per code, the first its reference."""
    made = await client.call_tool("create_product_system", {"name": name, "database": FIXTURE_DB})
    system_id = made.structured_content["value"]["id"]
    for code in codes:
        await client.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": code,
                "name": code,
                "unit": "unit",
                "reference_product": code,
            },
        )
    await client.call_tool(
        "update_product_system", {"product_system_id": system_id, "reference_process": codes[0]}
    )
    return system_id


async def _link(client: Client, host: str, code: str, linked: str, **pin: str) -> dict:
    out = await client.call_tool(
        "create_exchange",
        {
            "product_system_id": host,
            "code": code,
            "type": "product",
            "amount": 1.0,
            "input": {"kind": "system", "product_system_id": linked, **pin},
        },
    )
    return out.structured_content


async def test_a_link_is_pinned_to_the_linked_systems_current_state(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "part", "part")
        whole = await _created(client, "whole", "whole")
        written = await _link(client, whole, "whole", part)
        current = await client.call_tool("get_product_system", {"product_system_id": part})
    assert written["value"]["input"] == {
        "kind": "system",
        "product_system_id": part,
        "at_hash": current.structured_content["value"]["hash"],
        "case": None,
    }
    assert written["value"]["unit"] == "unit" and written["value"]["name"] == "part"


async def test_a_link_that_closes_a_cycle_is_refused_naming_it(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        a = await _created(client, "cycle_a", "a")
        b = await _created(client, "cycle_b", "b")
        await _link(client, a, "a", b)
        with pytest.raises(ToolError, match="cycle_b → cycle_a → cycle_b"):
            await _link(client, b, "b", a)


async def test_a_link_reaching_one_system_at_two_states_is_refused(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        c = await _created(client, "two_c", "c")
        b = await _created(client, "two_b", "b")
        await _link(client, b, "b", c)
        await client.call_tool(
            "create_process",
            {
                "product_system_id": c,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        a = await _created(client, "two_a", "a")
        await _link(client, a, "a", c)
        with pytest.raises(ToolError, match="rebase_links"):
            await _link(client, a, "a", b)


async def test_a_link_to_a_state_never_stored_is_not_found(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "ghost_part", "part")
        whole = await _created(client, "ghost_whole", "whole")
        with pytest.raises(ToolError, match="not_found"):
            await _link(client, whole, "whole", part, at_hash="0" * 64)


async def test_rebase_links_moves_the_pin_to_the_linked_systems_current_state(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "moving_part", "part")
        whole = await _created(client, "moving_whole", "whole")
        await _link(client, whole, "whole", part)
        await client.call_tool(
            "create_process",
            {
                "product_system_id": part,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        rebased = await client.call_tool("rebase_links", {"product_system_id": whole})
        current = await client.call_tool("get_product_system", {"product_system_id": part})
        with pytest.raises(ToolError, match="current"):
            await client.call_tool("rebase_links", {"product_system_id": whole})
    [moved] = rebased.structured_content["value"]
    assert moved["at_hash"] == current.structured_content["value"]["hash"]
    assert rebased.structured_content["entry"]["changes"]


async def test_a_linked_system_cannot_be_deleted_while_another_links_it(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "kept_part", "part")
        whole = await _created(client, "kept_whole", "whole")
        await _link(client, whole, "whole", part)
        with pytest.raises(ToolError, match="kept_whole"):
            await client.call_tool("delete_product_system", {"product_system_id": part})


async def test_a_linking_system_scores_decomposes_and_samples_through_the_link(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    args = {"product_system_id": str(widget.id), "method_id": GWP_ID}
    async with Client(full_server) as client:
        impact = await client.call_tool("calculate_impact", args)
        tree = await client.call_tool("contribution_analysis", {**args, "by": "path"})
        started = await client.call_tool(
            "start_monte_carlo", starting(widget, n=3, n_min=1, seed=1)
        )
        done = await finished(client, started.structured_content["value"]["id"])
    # the widget's own 2.49 and the frame's 6.672 per kilogram for a quarter kilogram
    assert impact.structured_content["value"]["scores"][0]["value"] == pytest.approx(4.158)
    children = tree.structured_content["value"]["root"]["children"]
    assert any(
        c["ref"] and c["ref"]["kind"] == "linked" and c["ref"]["product_system_id"] == str(frame.id)
        for c in children
    )
    assert done["status"] == "done"


async def test_a_credit_loop_inside_a_linked_system_is_named_with_that_system(
    full_server: FastMCP, context: ServerContext, credited_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        user = await _created(client, "credit_user", "user")
        await _link(client, user, "user", str(credited_stored.id))
        out = await client.call_tool(
            "calculate_impact", {"product_system_id": user, "method_id": GWP_ID}
        )
    value = out.structured_content["value"]
    # the credited widget scores 2.079, and the user takes one of it
    assert value["scores"][0]["value"] == pytest.approx(2.079)
    assert value["credit_loops"] == []
    [loop] = value["linked_credit_loops"]
    assert (loop["product_system_id"], loop["codes"]) == (
        str(credited_stored.id),
        ["frame", "widget"],
    )


async def test_validation_names_a_link_behind_its_system_until_it_is_rebased(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "checked_part", "part")
        whole = await _created(client, "checked_whole", "whole")
        await _link(client, whole, "whole", part)
        await client.call_tool(
            "create_process",
            {
                "product_system_id": part,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        behind = await client.call_tool("validate_product_system", {"product_system_id": whole})
        await client.call_tool("rebase_links", {"product_system_id": whole})
        current = await client.call_tool("validate_product_system", {"product_system_id": whole})

    def cases(out: CallToolResult) -> dict[str, bool]:
        return {c["id"]: c["passed"] for c in out.structured_content["value"]["cases"]}

    assert cases(behind)["links_current"] is False and cases(current)["links_current"] is True


async def test_a_link_stays_current_through_a_case_of_its_system_and_stales_on_an_edit(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "cased_part", "part")
        whole = await _created(client, "cased_whole", "whole")
        await client.call_tool(
            "set_parameters",
            {"product_system_id": part, "parameters": [{"name": "k", "value": 1.0}]},
        )
        await _link(client, whole, "whole", part)
        await client.call_tool(
            "set_parameters",
            {"product_system_id": part, "cases": [{"name": "double", "values": {"k": 2.0}}]},
        )
        cased = await client.call_tool("validate_product_system", {"product_system_id": whole})
        await client.call_tool(
            "set_parameters", {"product_system_id": part, "delete_cases": ["double"]}
        )
        uncased = await client.call_tool("validate_product_system", {"product_system_id": whole})
        await client.call_tool(
            "create_process",
            {
                "product_system_id": part,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        edited = await client.call_tool("validate_product_system", {"product_system_id": whole})

    def current(out: CallToolResult) -> bool:
        cases = {c["id"]: c["passed"] for c in out.structured_content["value"]["cases"]}
        return cases["links_current"]

    assert current(cased) and current(uncased) and not current(edited)


async def test_a_system_built_from_a_linked_part_validates_scores_samples_and_protects_it(
    full_server: FastMCP,
) -> None:
    steel = {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]}
    elec = {"kind": "background", "database": FIXTURE_DB, "id": CODES["elec"]}
    co2 = {"kind": "elementary_flow", "database": FIXTURE_BIO, "id": FLOW_IDS["co2"]}
    async with Client(full_server) as client:
        frame = await _created(client, "accepted_frame", "frame")
        widget = await _created(client, "accepted_widget", "widget")
        await client.call_tool(
            "update_process", {"product_system_id": frame, "code": "frame", "unit": "kilogram"}
        )
        for system, code, amount, input_ in (
            (frame, "frame", 2.4, steel),
            (widget, "widget", 0.5, steel),
            (widget, "widget", 1.0, elec),
        ):
            await client.call_tool(
                "create_exchange",
                {
                    "product_system_id": system,
                    "code": code,
                    "type": "product",
                    "amount": amount,
                    "input": input_,
                },
            )
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": widget,
                "code": "widget",
                "type": "elementary",
                "amount": 0.1,
                "input": co2,
            },
        )
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": widget,
                "code": "widget",
                "type": "product",
                "amount": 0.25,
                "input": {"kind": "system", "product_system_id": frame},
            },
        )
        report = await client.call_tool("validate_product_system", {"product_system_id": widget})
        args = {"product_system_id": widget, "method_id": GWP_ID}
        impact = await client.call_tool("calculate_impact", args)
        tree = await client.call_tool("contribution_analysis", {**args, "by": "path"})
        sampled = await client.call_tool(
            "calculate_impact", {**args, "monte_carlo": {"n": 3, "n_min": 1, "seed": 1}}
        )
        with pytest.raises(ToolError, match="accepted_widget"):
            await client.call_tool("delete_product_system", {"product_system_id": frame})
        with pytest.raises(ToolError, match="cycle"):
            await _link(client, frame, "frame", widget)
    assert report.structured_content["value"]["is_valid"]
    # the widget's own 2.49 and the frame's 6.672 per kilogram for a quarter kilogram
    assert impact.structured_content["value"]["scores"][0]["value"] == pytest.approx(4.158)
    children = tree.structured_content["value"]["root"]["children"]
    assert any(c["ref"] and c["ref"]["kind"] == "linked" for c in children)
    assert sampled.structured_content["value"]["uncertainty"]["n"] == 3


async def test_a_link_naming_a_case_calculates_that_case(
    full_server: FastMCP, context: ServerContext
) -> None:
    frame = frame_system()
    frame.id = uid("fixture-product_system", "frame-cased")
    frame.name = "frame_cased"
    frame.process("frame").exchanges[1].formula = "steel_kg"
    frame.parameters = [Parameter(name="steel_kg", value=2.4)]
    frame.cases = [Case(name="light", values={"steel_kg": 1.2})]
    await context.storage.put_product_system(frame, context.actor, "created")
    widget = widget_linking(frame)
    widget.id = uid("fixture-product_system", "widget-light")
    widget.name = "widget_light"
    for exchange in widget.process("widget").exchanges:
        if isinstance(exchange.input, SystemRef):
            exchange.input = exchange.input.model_copy(update={"case": "light"})
    await context.storage.put_product_system(widget, context.actor, "created")
    async with Client(full_server) as client:
        out = await client.call_tool(
            "calculate_impact", {"product_system_id": str(widget.id), "method_id": GWP_ID}
        )
        missing = await _created(client, "missing_case_user", "user")
        with pytest.raises(ToolError, match="ghost"):
            await _link(client, missing, "user", str(frame.id), case="ghost")
    # a quarter kilogram of the light frame's 3.336 in place of the frame's 6.672
    assert out.structured_content["value"]["scores"][0]["value"] == pytest.approx(3.324)
    assert content_hash(widget) != content_hash(widget_linking(frame))


async def test_a_case_a_link_names_is_current_until_its_values_change_and_cannot_be_deleted(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "named_part", "part")
        whole = await _created(client, "named_whole", "whole")
        await client.call_tool(
            "set_parameters",
            {
                "product_system_id": part,
                "parameters": [{"name": "k", "value": 1.0}],
                "cases": [
                    {"name": "double", "values": {"k": 2.0}},
                    {"name": "other", "values": {"k": 3.0}},
                ],
            },
        )
        await _link(client, whole, "whole", part, case="double")
        await client.call_tool(
            "set_parameters",
            {"product_system_id": part, "cases": [{"name": "other", "values": {"k": 4.0}}]},
        )
        other_moved = await client.call_tool(
            "validate_product_system", {"product_system_id": whole}
        )
        with pytest.raises(ToolError, match="named_whole"):
            await client.call_tool(
                "set_parameters", {"product_system_id": part, "delete_cases": ["double"]}
            )
        await client.call_tool(
            "set_parameters",
            {"product_system_id": part, "cases": [{"name": "double", "values": {"k": 5.0}}]},
        )
        named_moved = await client.call_tool(
            "validate_product_system", {"product_system_id": whole}
        )

    def current(out: CallToolResult) -> bool:
        cases = {c["id"]: c["passed"] for c in out.structured_content["value"]["cases"]}
        return cases["links_current"]

    assert current(other_moved) and not current(named_moved)


async def test_a_link_to_a_case_its_system_no_longer_carries_is_reported_behind(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "dropped_part", "part")
        whole = await _created(client, "dropped_whole", "whole")
        cased = await client.call_tool(
            "set_parameters",
            {
                "product_system_id": part,
                "parameters": [{"name": "k", "value": 1.0}],
                "cases": [{"name": "double", "values": {"k": 2.0}}],
            },
        )
        at_hash = cased.structured_content["entry"]["result_hash"]
        await client.call_tool(
            "set_parameters", {"product_system_id": part, "delete_cases": ["double"]}
        )
        await _link(client, whole, "whole", part, at_hash=at_hash, case="double")
        out = await client.call_tool("validate_product_system", {"product_system_id": whole})
    cases = {c["id"]: c["passed"] for c in out.structured_content["value"]["cases"]}
    assert cases["links_resolve"] and not cases["links_current"]


async def test_a_write_answer_names_the_systems_whose_links_it_left_behind(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "consequence_part", "part")
        whole = await _created(client, "consequence_whole", "whole")
        await _link(client, whole, "whole", part)
        out = await client.call_tool(
            "create_process",
            {
                "product_system_id": part,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        quiet = await client.call_tool(
            "update_product_system", {"product_system_id": part, "notes": "checked"}
        )
    found = out.structured_content["consequences"]
    assert [link["name"] for link in found["links_behind"]] == ["consequence_whole"]
    assert found["scenarios_staled"] == []
    calm = quiet.structured_content["consequences"]
    assert (calm["scenarios_staled"], calm["links_behind"]) == ([], [])
    # the part's lone processes are issues the answer reports on every write
    assert "island_activities_detected" in {i["code"] for i in calm["issues"]}
    # stated without a remedy: "delete them" is validate_product_system's to propose
    assert all("suggestion" not in i for i in calm["issues"])


async def test_a_calculation_answers_the_score_and_names_the_link_behind(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        part = await _created(client, "behind_part", "part")
        whole = await _created(client, "behind_whole", "whole")
        await _link(client, whole, "whole", part)
        await client.call_tool(
            "create_process",
            {
                "product_system_id": part,
                "code": "more",
                "name": "more",
                "unit": "unit",
                "reference_product": "more",
            },
        )
        out = await client.call_tool(
            "calculate_impact", {"product_system_id": whole, "method_id": GWP_ID}
        )
    value = out.structured_content["value"]
    assert value["scores"][0]["value"] == pytest.approx(0.0)
    assert [link["name"] for link in value["links_behind"]] == ["behind_part"]
