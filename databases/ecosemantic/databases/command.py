"""The command line a source answers with: its subcommands, its answer as one JSON document, and
its exit code."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.errors import EcoSemanticError, error_payload


@dataclass(frozen=True)
class Command:
    """One subcommand: what it does, in a line, and what runs it."""

    help: str
    run: Callable[[argparse.Namespace], object]


def _document(answer: object) -> object:
    """A dataclass answer as the fields its repr shows, and any other answer as it stands."""
    if isinstance(answer, type) or not dataclasses.is_dataclass(answer):
        return answer
    return {
        field.name: getattr(answer, field.name)
        for field in dataclasses.fields(answer)
        if field.repr
    }


def _serialised(value: object) -> object:
    """A value JSON does not carry on its own: a dataclass as the dict `dataclasses.asdict` gives
    it, and a path as its string."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, type) or not dataclasses.is_dataclass(value):
        raise TypeError(f"{type(value).__name__} does not go into a document")
    return dataclasses.asdict(value)


def main(
    parser: argparse.ArgumentParser,
    commands: Mapping[str, Command],
    argv: list[str] | None,
    *,
    code: Callable[[object], int],
) -> int:
    """Run one command, its answer printed as one JSON document, and answer the code it carries;
    a typed error is its envelope on stderr and 1."""
    args = parser.parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            answer = commands[args.command].run(args)
    except EcoSemanticError as exc:
        print(error_payload(exc).model_dump_json(), file=sys.stderr)
        return 1
    print(json.dumps(_document(answer), default=_serialised))
    return code(answer)
