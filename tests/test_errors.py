from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from ecosemantic.errors import (
    Cancelled,
    Conflict,
    ErrorEnvelope,
    Invalid,
    OtherBuild,
    StaleScenario,
    Unauthorised,
    Unavailable,
    build_label,
    error_kind,
    error_line,
    error_payload,
    error_status,
    failure_payload,
    field_error,
    unreadable,
)


def test_a_typed_error_renders_as_its_envelope() -> None:
    assert error_payload(Invalid("bad")) == ErrorEnvelope(error="invalid", message="bad")
    assert error_payload(Invalid("bad")).model_dump() == {
        "error": "invalid",
        "message": "bad",
        "details": {},
    }
    assert error_status(error_kind(Invalid("bad"))) == 400


def test_a_failure_that_is_no_typed_error_renders_as_failed() -> None:
    assert failure_payload("the worker died") == ErrorEnvelope(
        error="failed", message="the worker died"
    )


def test_cancelled_is_its_own_kind_answering_409() -> None:
    stopped = Cancelled("the install stopped where it last checked")
    assert error_payload(stopped) == ErrorEnvelope(error="cancelled", message=str(stopped))
    assert error_kind(stopped) == "cancelled"
    assert error_status("cancelled") == 409
    assert not isinstance(stopped, Conflict)


def test_a_missing_secret_renders_as_unauthorised() -> None:
    refused = Unauthorised("the token in the link is required")
    assert error_payload(refused).error == "unauthorised"
    assert error_payload(refused).details == {}
    assert error_status(error_kind(refused)) == 401
    hinted = Unauthorised("a credential is entered only from this machine", hint="run setup")
    assert error_payload(hinted).details == {"hint": "run setup"}


def test_a_surface_adds_its_own_remedy_to_the_error_it_renders() -> None:
    stale = StaleScenario("half", "a" * 64, "b" * 64)
    plain = error_payload(stale)
    assert plain.error == "invalid" and plain.message == str(stale)
    assert plain.details == {
        "scenario": "half",
        "pinned_to": "a" * 64,
        "at": "b" * 64,
        "moved_by": None,
    }
    worded = error_payload(stale, {StaleScenario: "rebase it"})
    assert worded.message == f"{stale}; rebase it"
    assert error_payload(Invalid("bad"), {StaleScenario: "rebase it"}).message == "bad"


def test_an_error_line_joins_its_location_with_dots_before_its_message() -> None:
    assert error_line(("processes", 0, "code"), "Field required") == (
        "processes.0.code: Field required"
    )


def test_an_error_line_at_the_input_itself_is_its_message_alone() -> None:
    assert error_line((), "Invalid JSON: expected ident at line 1 column 2") == (
        "Invalid JSON: expected ident at line 1 column 2"
    )


def test_a_validation_error_renders_its_first_field_and_message() -> None:
    class Inner(BaseModel):
        count: int

    class Outer(BaseModel):
        inner: Inner

    with pytest.raises(ValidationError) as caught:
        Outer.model_validate({"inner": {"count": "many"}})
    assert field_error(caught.value) == (
        "inner.count: Input should be a valid integer, unable to parse string as an integer"
    )


def test_a_build_is_labelled_by_its_first_twelve_characters() -> None:
    assert build_label(None) == "no build"
    assert build_label("0123456789abcdef") == "build 0123456789ab"
    assert build_label("0123456789") == "build 0123456789"
    assert str(OtherBuild("widget", "fixture", "0" * 64, "a" * 64)) == (
        "'widget' names build 000000000000 of 'fixture'; this store holds build aaaaaaaaaaaa"
    )


def test_a_stored_document_this_version_cannot_read_is_one_sentence() -> None:
    class Stored(BaseModel):
        count: int

    with pytest.raises(ValidationError) as caught:
        Stored.model_validate({"count": "many"})
    refused = unreadable("requests.jsonl line 3", caught.value, "remove it")
    assert isinstance(refused, Unavailable)
    assert str(refused) == (
        "requests.jsonl line 3 cannot be read by this version: count: Input should be a valid"
        " integer, unable to parse string as an integer"
    )
    assert refused.hint == "remove it"
    assert error_kind(refused) == "unavailable"
