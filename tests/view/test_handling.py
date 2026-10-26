from __future__ import annotations

import json

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ecosemantic.errors import NotFound
from ecosemantic.model.entities import Actor
from ecosemantic.view.handling import ToolRefused, answering, created, working


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


async def test_the_boundary_answers_a_typed_error_and_a_refused_tool_call_as_envelopes() -> None:
    @answering
    async def missing(request: Request) -> Response:
        raise NotFound("no such thing")

    @answering
    async def refused(request: Request) -> Response:
        raise ToolRefused(JSONResponse({"error": "conflict"}, status_code=409))

    first = await missing(_request())
    assert first.status_code == 404 and json.loads(bytes(first.body))["error"] == "not_found"
    assert (await refused(_request())).status_code == 409


async def test_the_boundary_lets_any_other_error_through() -> None:
    @answering
    async def broken(request: Request) -> Response:
        raise RuntimeError("not a typed error")

    with pytest.raises(RuntimeError):
        await broken(_request())


def test_a_working_directory_goes_on_the_way_out_unless_it_is_kept() -> None:
    with working("ecosemantic-test-") as gone:
        assert gone.is_dir()
    assert not gone.exists()
    with working("ecosemantic-test-", keep=True) as kept:
        pass
    assert kept.is_dir()
    kept.rmdir()


def test_a_kept_working_directory_still_goes_when_the_request_fails() -> None:
    with pytest.raises(RuntimeError), working("ecosemantic-test-", keep=True) as work:
        raise RuntimeError("the render failed")
    assert not work.exists()


def test_a_write_answers_what_it_made_under_201() -> None:
    answered = created(Actor(kind="person", name="Ada"))
    assert answered.status_code == 201
    assert json.loads(answered.body)["name"] == "Ada"
