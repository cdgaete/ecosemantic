"""The typed errors the core raises. A layer that cannot answer raises rather than approximates."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, JsonValue

if TYPE_CHECKING:
    from ecosemantic.model.entities import Method


class EcoSemanticError(Exception):
    """Base of every error the core raises."""


class NotFound(EcoSemanticError):
    """The named entity does not exist in this backend."""


class Invalid(EcoSemanticError):
    """The input is well-formed but wrong for the operation."""


class Refusal(BaseModel):
    """One cell a folder cannot be read at: where it is, what it held and why it is refused."""

    file: str
    row: int
    column: str
    found: str
    reason: str


class Refused(Invalid):
    """A table folder holds cells that cannot be read; the error names every one of them."""

    def __init__(self, refusals: list[Refusal]) -> None:
        self.refusals = refusals
        first = refusals[0]
        super().__init__(
            f"{len(refusals)} cell(s) refused, first {first.file} row {first.row} "
            f"column {first.column!r}: {first.reason}"
        )


class StaleScenario(Invalid):
    """A scenario is pinned to a base the product system is not at; carries both pins and, when
    the log names it, the entry that moved the base, and leaves what to do about it to the
    surface that answers, since a tool can rebase and a folder cannot."""

    def __init__(
        self, name: str, pinned: str | None, at: str | None, moved_by: str | None = None
    ) -> None:
        self.name = name
        self.pinned = pinned
        self.at = at
        self.moved_by = moved_by
        moved = "" if moved_by is None else f"; {moved_by} moved it"
        super().__init__(
            f"scenario {name!r} is pinned to {pinned}, the product system is at {at}{moved}"
        )


class Conflict(EcoSemanticError):
    """The write is based on a state the store does not hold."""


class Cancelled(EcoSemanticError):
    """The work stopped because someone asked it to, at the last point it checked the request."""


class RunOpen(Conflict):
    """A run of this workspace is still open; carries its ids, so a caller can reach it."""

    def __init__(self, run_id: uuid.UUID, product_system_id: uuid.UUID, status: str) -> None:
        self.run_id = run_id
        self.product_system_id = product_system_id
        super().__init__(f"run {run_id} is {status}; one run at a time")


class OtherBuild(Conflict):
    """A product system names a build of its database other than the installed one, or none;
    carries both fingerprints, so a caller can install the build or move the system onto it."""

    def __init__(
        self, product_system: str, database: str, named: str | None, installed: str | None
    ) -> None:
        self.product_system = product_system
        self.database = database
        self.named = named
        self.installed = installed
        build = "no build" if named is None else f"build {named[:12]}"
        super().__init__(
            f"{product_system!r} names {build} of {database!r}; this store holds build "
            f"{str(installed)[:12]}"
        )


class Unavailable(EcoSemanticError):
    """The backend exists but cannot be reached now; `hint` names the remedy, if there is one."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class NotSupported(EcoSemanticError):
    """This backend does not answer this question."""


class Unauthorised(EcoSemanticError):
    """The call does not carry the secret the route requires, or comes from a peer the route
    refuses; `hint` names the remedy, if there is one."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class MethodNotFound(NotFound):
    """No method matched the reference; carries the nearest methods so the caller can correct."""

    def __init__(self, database: str, reference: str, suggestions: list[Method]) -> None:
        self.database = database
        self.reference = reference
        self.suggestions = suggestions
        nearest = "; ".join(f"{s.id} {s.spec}" for s in suggestions)
        super().__init__(f"no method {reference!r} in {database!r}; nearest: {nearest}")


_KIND: dict[type[EcoSemanticError], tuple[str, int]] = {
    Cancelled: ("cancelled", 409),
    MethodNotFound: ("method_not_found", 404),
    NotFound: ("not_found", 404),
    Invalid: ("invalid", 400),
    Conflict: ("conflict", 409),
    Unavailable: ("unavailable", 503),
    NotSupported: ("not_supported", 501),
    Unauthorised: ("unauthorised", 401),
}
_STATUS: dict[str, int] = dict(_KIND.values())


def error_kind(exc: EcoSemanticError) -> str:
    """The envelope's name for a typed error; the most specific class wins."""
    for kind, (name, _status) in _KIND.items():
        if isinstance(exc, kind):
            return name
    raise TypeError(f"{type(exc).__name__} is not a typed core error")


def error_status(kind: str) -> int:
    """The HTTP status an error kind answers with; an unknown kind raises."""
    try:
        return _STATUS[kind]
    except KeyError as error:
        raise ValueError(f"{kind!r} is not an error kind") from error


class ErrorEnvelope(BaseModel):
    """What a failure renders as wherever it is answered or recorded: its kind, its message and
    the details a caller can act on."""

    error: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


Remedies = Mapping[type[EcoSemanticError], str]


def error_payload(exc: EcoSemanticError, remedies: Remedies | None = None) -> ErrorEnvelope:
    """The envelope a typed error renders as: its kind, its message and its details. A surface
    that can name what its caller does next about a kind of error passes that remedy, and the
    message ends with it."""
    name = error_kind(exc)
    details: dict[str, JsonValue] = {}
    if isinstance(exc, MethodNotFound):
        details["suggestions"] = [{"id": m.id, "spec": m.spec} for m in exc.suggestions]
    if isinstance(exc, (Unavailable, Unauthorised)) and exc.hint is not None:
        details["hint"] = exc.hint
    if isinstance(exc, Refused):
        details["refusals"] = [refusal.model_dump(mode="json") for refusal in exc.refusals]
    if isinstance(exc, RunOpen):
        details["run_id"] = str(exc.run_id)
        details["product_system_id"] = str(exc.product_system_id)
    if isinstance(exc, OtherBuild):
        details["database"] = exc.database
        details["named"] = exc.named
        details["installed"] = exc.installed
    if isinstance(exc, StaleScenario):
        details["scenario"] = exc.name
        details["pinned_to"] = exc.pinned
        details["at"] = exc.at
        details["moved_by"] = exc.moved_by
    said = [remedy for kind, remedy in (remedies or {}).items() if isinstance(exc, kind)]
    return ErrorEnvelope(error=name, message="; ".join([str(exc), *said]), details=details)


def failure_payload(message: str) -> ErrorEnvelope:
    """The envelope of a failure that is no typed error: a process that crashed or is gone."""
    return ErrorEnvelope(error="failed", message=message)
