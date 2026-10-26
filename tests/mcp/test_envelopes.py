from __future__ import annotations

import asyncio
import json
import typing
import uuid

import pytest
from fastmcp.exceptions import ToolError

from ecosemantic.errors import (
    Conflict,
    EcoSemanticError,
    Invalid,
    MethodNotFound,
    NotFound,
    NotSupported,
    RunOpen,
    Unavailable,
    error_kind,
    error_status,
)
from ecosemantic.mcp import discovery
from ecosemantic.mcp.envelopes import (
    Answer,
    Listing,
    as_uuid,
    bound,
    boundary,
    carried,
    empty_search_hint,
    listing,
    page_hint,
    serialised,
    suggestion_hint,
    tool_error,
)
from ecosemantic.model.entities import Method, method_id
from ecosemantic.model.summary import Summary
from ecosemantic.ports.types import Page
from tests.model.test_summary import GWP, hit


def test_listing_carries_the_page_and_hints_the_cursor_only_when_there_is_more() -> None:
    page = Page[str](items=["a", "b"], has_more=True, next_cursor="2")
    out = listing(page)
    assert isinstance(out, Listing)
    assert out.items == ["a", "b"] and out.has_more is True and out.next_cursor == "2"
    assert out.hint == "more results; call again with cursor='2'"
    assert listing(Page[str](items=["a"], has_more=False)).hint is None
    assert listing(page, "custom").hint == "custom"


def test_tool_error_names_the_kind_and_message() -> None:
    error = tool_error(NotFound("no database 'x'"))
    assert isinstance(error, ToolError)
    payload = json.loads(str(error))
    assert payload["error"] == "not_found"
    assert payload["message"] == "no database 'x'"
    assert payload["details"] == {}


def test_tool_error_maps_every_typed_error() -> None:
    assert json.loads(str(tool_error(Invalid("bad"))))["error"] == "invalid"
    assert json.loads(str(tool_error(Unavailable("gone"))))["error"] == "unavailable"


def test_tool_error_carries_method_suggestions() -> None:
    spec = "db > f > c > i"
    m = Method(
        id=method_id(spec),
        tuple=("db", "f", "c", "i"),
        spec=spec,
        unit="u",
        impact_method="f",
        impact_category="c",
        indicator="i",
    )
    payload = json.loads(str(tool_error(MethodNotFound("db", "wrong", [m]))))
    assert payload["error"] == "method_not_found"
    assert payload["details"]["suggestions"] == [{"id": m.id, "spec": spec}]


def test_hints_say_what_to_do_next() -> None:
    assert "location" in empty_search_hint({"location": "CH", "unit": None}, True)
    assert "name fewer words" in empty_search_hint({}, False)
    assert "location" not in empty_search_hint({"location": "CH"}, False)
    assert "5" in (page_hint(Page[str](items=["a"], has_more=True, next_cursor="5")) or "")
    assert page_hint(Page[str](items=["a"], has_more=False)) is None
    assert "m_" in suggestion_hint("climate change", "m_abc1234567")


def test_an_unavailable_error_carries_its_remedy() -> None:
    assert "unavailable" == json.loads(str(tool_error(Unavailable("gone"))))["error"]
    assert json.loads(str(tool_error(Unavailable("gone"))))["details"] == {}
    with_remedy = json.loads(str(tool_error(Unavailable("gone", hint="run setup"))))
    assert with_remedy["details"] == {"hint": "run setup"}


def test_as_uuid_rejects_what_is_not_one() -> None:
    assert str(as_uuid("6f1b5a5e-0c3e-4b52-9a1e-2f0d6c1a7d10")).startswith("6f1b5a5e")
    with pytest.raises(Invalid):
        as_uuid("tshirt")


def test_unknown_error_is_not_swallowed() -> None:
    with pytest.raises(TypeError):
        tool_error(ValueError("not a typed error"))


def test_error_status_answers_every_kind_and_rejects_unknown() -> None:
    expected: dict[EcoSemanticError, int] = {
        NotFound("no database 'x'"): 404,
        MethodNotFound("db", "wrong", []): 404,
        Invalid("bad"): 400,
        Conflict("stale"): 409,
        Unavailable("gone"): 503,
        NotSupported("no"): 501,
    }
    for exc, status in expected.items():
        assert error_status(error_kind(exc)) == status
    with pytest.raises(ValueError):
        error_status("nope")


def test_a_run_holding_the_slot_is_named_in_the_details() -> None:
    run_id, system_id = uuid.UUID(int=7), uuid.UUID(int=8)
    payload = json.loads(str(tool_error(RunOpen(run_id, system_id, "running"))))
    assert payload["error"] == "conflict"
    assert payload["message"] == f"run {run_id} is running; one run at a time"
    assert payload["details"] == {"run_id": str(run_id), "product_system_id": str(system_id)}


def test_a_listing_summarises_its_page() -> None:
    summary = Listing(items=[hit(1), hit(2)], has_more=True).summarise()
    assert summary.count == 2 and summary.more and summary.items[0].ref == "p1"


def test_an_answer_summarises_what_its_value_can() -> None:
    assert Answer(value=[GWP]).summarise() == Summary(count=1, items=[GWP.summary_item()])
    assert Answer(value={"anything": 1}).summarise() is None


async def test_bound_registers_the_function_less_its_context() -> None:
    import inspect

    from ecosemantic.mcp.envelopes import bound

    async def tool(context: str, name: str, count: int = 2) -> str:
        return f"{context}:{name}:{count}"

    registered = bound(tool, "ctx")
    assert list(inspect.signature(registered).parameters) == ["name", "count"]
    assert inspect.signature(registered).parameters["count"].default == 2
    assert "context" not in registered.__annotations__
    assert registered.__name__ == "tool"
    assert await registered(name="widget") == "ctx:widget:2"


def test_a_wrapper_carries_the_annotations_of_the_function_it_wraps() -> None:
    async def wrapped() -> None:
        return None

    async def wrapper() -> None:
        return None

    # bound assigns a tool's annotations as a mapping; from Python 3.14 functools.wraps copies
    # only __annotate__, which leaves its wrapper with none
    wrapped.__annotations__ = {"return": "Answer[list[Database]]"}
    wrapper.__annotations__ = {}
    assert carried(wrapper, wrapped).__annotations__ == {"return": "Answer[list[Database]]"}


@pytest.mark.parametrize("wrap", [boundary, serialised(lambda _: asyncio.Lock())])
def test_a_registered_tool_s_annotations_resolve_through_its_wrappers(
    wrap: typing.Callable[..., typing.Any],
) -> None:
    hints = typing.get_type_hints(wrap(bound(discovery.list_databases, object())))
    assert hints == {"return": typing.get_type_hints(discovery.list_databases)["return"]}
