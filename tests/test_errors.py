from __future__ import annotations

from ecosemantic.errors import (
    Cancelled,
    Conflict,
    ErrorEnvelope,
    Invalid,
    StaleScenario,
    Unauthorised,
    error_kind,
    error_payload,
    error_status,
    failure_payload,
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
