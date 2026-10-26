"""The command line: the four subcommands and the download that answers one."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, get_args

from ecoinvent_interface import EcoinventRelease, Settings

from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.download import download
from ecosemantic.databases.ecoinvent.probe import probe, report
from ecosemantic.databases.ecoinvent.profile import (
    Profile,
    default_profile,
    pinned,
    profiled,
)
from ecosemantic.databases.ecoinvent.release import Release, SystemModel, sha256
from ecosemantic.databases.ecoinvent.validate import TOLERANCE, Validation, validate
from ecosemantic.errors import EcoSemanticError, NotFound, Unavailable, error_payload
from ecosemantic.package.base_writer import Written

Handler = Callable[[argparse.Namespace], object]


@dataclass(frozen=True)
class Command:
    """One subcommand: what it does, in a line, and what runs it."""

    help: str
    run: Handler


def _release(args: argparse.Namespace) -> Release:
    """Fetch the five files of the release a command names."""
    settings = Settings()
    if not settings.username or not settings.password:
        raise Unavailable("EI_USERNAME and EI_PASSWORD must be set")
    return download(args.version, cast(SystemModel, args.system_model), EcoinventRelease(settings))


def _download(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    """Fetch a release's five files and answer each one's path and SHA-256."""
    release = _release(args)
    return {
        role: {"path": str(path), "sha256": sha256(path)} for role, path in release.files().items()
    }


def _pinned(release: Release) -> Profile:
    """A release's profile, or the default layout when the release has none."""
    if (release.version, release.system_model) not in profiled():
        return default_profile(release)
    return pinned(release.version, release.system_model)


def _required(args: argparse.Namespace, release: Release) -> Profile:
    """The profile a build or a validation requires, or the default layout under --no-profile."""
    if args.no_profile:
        return default_profile(release)
    try:
        return pinned(release.version, release.system_model)
    except NotFound as absent:
        raise NotFound(f"{absent}; pass --no-profile to use the default layout") from absent


def _probe(args: argparse.Namespace) -> dict[str, object]:
    """Fetch a release, pin it to its profile when one exists, and list what a build cannot read."""
    release = _release(args)
    profile = default_profile(release) if args.no_profile else _pinned(release)
    return report(probe(release, profile))


def _build(args: argparse.Namespace) -> Written:
    """Build a release into one bundle under --out."""
    release = _release(args)
    return build(release, _required(args, release), args.out, datetime.now(UTC))


def _validate(args: argparse.Namespace) -> Validation:
    """Compare a built bundle with the release's own matrices and cumulative LCIA."""
    release = _release(args)
    profile = _required(args, release)
    compiled = args.compiled
    if compiled is None:
        compiled = Path(tempfile.mkdtemp(prefix="ecosemantic-validate-")) / "background"
    return validate(
        release,
        args.bundle,
        compiled,
        tolerance=args.tolerance,
        workbook_disagrees=profile.workbook_disagrees,
        matrix_reference_tolerance=profile.matrix_reference_tolerance,
    )


COMMANDS: dict[str, Command] = {
    "download": Command("Fetch one release's five files.", _download),
    "probe": Command("List what a release holds against what a build reads.", _probe),
    "build": Command("Write one release as an openLCA JSON-LD bundle.", _build),
    "validate": Command("Compare a built bundle with ecoinvent's own results.", _validate),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecosemantic-databases ecoinvent",
        description="Build a native EcoSemantic bundle from an ecoinvent release.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, command in COMMANDS.items():
        sub = subcommands.add_parser(name, help=command.help)
        sub.add_argument("version")
        sub.add_argument("--system-model", required=True, choices=get_args(SystemModel))
        if name == "build":
            sub.add_argument("--out", required=True, type=Path)
        if name == "validate":
            sub.add_argument("--bundle", required=True, type=Path)
            sub.add_argument("--compiled", type=Path, default=None)
            sub.add_argument("--tolerance", type=float, default=TOLERANCE)
        if name != "download":
            sub.add_argument("--no-profile", action="store_true")
    return parser


def _refused(exc: EcoSemanticError) -> int:
    """Render one typed error as its envelope on stderr."""
    print(error_payload(exc).model_dump_json(), file=sys.stderr)
    return 1


def _jsonable(answer: object) -> object:
    """A dataclass answer as JSON, a path rendered as text."""
    if isinstance(answer, Written):
        return {**dataclasses.asdict(answer), "bundle": str(answer.bundle)}
    if isinstance(answer, Validation):
        return dataclasses.asdict(answer)
    return answer


def main(argv: list[str] | None = None) -> int:
    """Run one command; 0 on success and 1 on a typed error or a validation that found a
    difference."""
    args = _parser().parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            answer = COMMANDS[args.command].run(args)
    except EcoSemanticError as exc:
        return _refused(exc)
    print(json.dumps(_jsonable(answer)))
    return 1 if isinstance(answer, Validation) and answer.mismatches else 0
