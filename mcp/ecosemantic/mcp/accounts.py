"""The advice a person reads where an account is entered, and the answer the page's entry route
gives."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, computed_field

from ecosemantic.compute.accounts import VARIABLES
from ecosemantic.mcp.context import AccountStart
from ecosemantic.ports.types import CredentialKind, DatabaseSource

Reach = Literal["here", "bridge", "network"]

ACCOUNTS_PATH = "/accounts"

_WHY = (
    "Database accounts are entered on the computer where EcoSemantic runs, so the password "
    "stays on that computer and never passes through the internet or a chat."
)
_TRAY = (
    "On the computer where EcoSemantic runs, click the EcoSemantic icon beside the clock in the "
    "taskbar (it may sit under the ^ arrow) and choose Database accounts…"
)
_ARRIVAL = {"bridge": "through the bridge", "network": "across the network"}


def _setup(source: DatabaseSource) -> str:
    """The command line that installs one source from its terminal, in backticks; an ecoinvent
    release names the version its profile pins."""
    if source.name == "ecoinvent":
        return "`ecosemantic setup ecoinvent <version>`"
    return f"`ecosemantic setup {source.name}`"


def _named(kind: CredentialKind) -> str:
    """The variables one account kind travels in, and the token an account with a second factor
    takes."""
    username, password, token = VARIABLES[kind]
    variables = f"{username} and {password}"
    if token is None:
        return variables
    return f"{variables} (and {token} for an account with a second factor)"


def _variables(needed: Sequence[DatabaseSource]) -> str:
    """The variables a server is started with to hold the accounts of the sources named, or of
    every kind where no source is named."""
    kinds = {source.credential for source in needed if source.credential is not None}
    return "; or ".join(_named(kind) for kind in VARIABLES if not kinds or kind in kinds)


def _steps(entry: AccountStart, needed: Sequence[DatabaseSource]) -> str:
    """What a person does to give the engine the accounts of the sources needed, by start."""
    if entry.start == "tray":
        return _TRAY
    setup = " or ".join(_setup(source) for source in needed) or "`ecosemantic setup <source>`"
    if entry.start == "terminal" and entry.screen is not None:
        return (
            f"Open {entry.screen} in a browser on the computer where EcoSemantic runs, "
            f"or run {setup} there."
        )
    return (
        f"On the computer where EcoSemantic runs, run {setup}, or start EcoSemantic with "
        f"{_variables(needed)} set."
    )


class Advice(BaseModel):
    """What a person reads: why an account is entered where it is, and the steps that enter it."""

    why: str
    steps: str

    def said(self) -> str:
        """The two parts as the one passage the page and the agent show."""
        return f"{self.why} {self.steps}"


def account_advice(
    entry: AccountStart,
    reach: Reach | None = None,
    needed: Sequence[DatabaseSource] = (),
) -> Advice:
    """The advice for an engine started as the start says, for a request that reached it over the
    reach given, about the sources whose account the engine does not hold; no source named means
    any source."""
    why = _WHY
    if reach is not None and reach != "here":
        why = f"This page reaches EcoSemantic {_ARRIVAL[reach]}. {_WHY}"
    return Advice(why=why, steps=_steps(entry, needed))


class AccountEntry(BaseModel):
    """What the page reads before an account is typed: how the request reached the engine, the
    advice where that is not the engine's own computer, and the bridge page's address."""

    reach: Reach
    why: str | None
    steps: str | None
    page: str | None

    @computed_field
    @property
    def here(self) -> bool:
        """Whether the request reached the engine on its own computer, the one reach that enters
        an account."""
        return self.reach == "here"


def entry_for(start: AccountStart, reach: Reach) -> AccountEntry:
    """The entry route's answer for an engine started as the start says and a request that
    reached it over the reach given."""
    if reach == "here":
        return AccountEntry(reach=reach, why=None, steps=None, page=start.page)
    advice = account_advice(start, reach)
    return AccountEntry(reach=reach, why=advice.why, steps=advice.steps, page=start.page)
