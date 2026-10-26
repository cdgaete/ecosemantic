"""The activity port over a directory: one JSON Lines file per agent under the systems
directory."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from filelock import FileLock
from pydantic import ValidationError

from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.ports.types import (
    AgentSummary,
    Call,
    CallDraft,
    agents_of,
    checked_agent,
    selected,
)

ACTIVITY_DIR = "activity"
SUFFIX = ".jsonl"


class FilesystemActivity:
    """Recorded calls as one line each, appended to the file of the agent that made them.

    Two processes over one directory may serve agents of one name, so a file is appended to and
    read under a lock both take.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _folder(self) -> Path:
        return self.root / ACTIVITY_DIR

    def _lock(self, agent: str) -> FileLock:
        return FileLock(self._folder() / f"{agent}.lock")

    def _append(self, call: Call) -> Call:
        self._folder().mkdir(parents=True, exist_ok=True)
        with self._lock(call.agent):
            with (self._folder() / f"{call.agent}{SUFFIX}").open("a", encoding="utf-8") as handle:
                handle.write(call.model_dump_json() + "\n")
        return call

    def _read(self, agent: str | None) -> list[Call]:
        if not self._folder().is_dir():
            return []
        if agent is not None:
            files = [self._folder() / f"{checked_agent(agent)}{SUFFIX}"]
        else:
            files = sorted(self._folder().glob(f"*{SUFFIX}"))
        calls: list[Call] = []
        for file in files:
            if file.is_file():
                with self._lock(file.name.removesuffix(SUFFIX)):
                    calls.extend(_parsed(file))
        return calls

    async def record(self, draft: CallDraft) -> Call:
        call = Call(id=uuid.uuid4(), **draft.model_dump())
        return await asyncio.to_thread(self._append, call)

    async def list_calls(
        self,
        agent: str | None = None,
        product_system_id: uuid.UUID | None = None,
        after: datetime | None = None,
    ) -> list[Call]:
        calls = await asyncio.to_thread(self._read, agent)
        return selected(calls, agent, product_system_id, after)

    async def get_call(self, call_id: uuid.UUID) -> Call:
        for call in await asyncio.to_thread(self._read, None):
            if call.id == call_id:
                return call
        raise NotFound(f"no call {call_id}")

    async def list_agents(self) -> list[AgentSummary]:
        return agents_of(await asyncio.to_thread(self._read, None))


def _parsed(file: Path) -> list[Call]:
    """A file's calls, or Unavailable naming the file, the line and the first field this version
    cannot read in it."""
    calls: list[Call] = []
    for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            calls.append(Call.model_validate_json(line))
        except ValidationError as error:
            first = error.errors(include_url=False)[0]
            field = ".".join(str(part) for part in first["loc"])
            raise Unavailable(
                f"{file.name} line {number} cannot be read by this version: "
                f"{field}: {first['msg']}",
                hint=f"remove {file} to read the activity again",
            ) from error
    return calls
