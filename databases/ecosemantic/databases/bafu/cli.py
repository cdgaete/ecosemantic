"""The command line: the subcommands a BAFU source answers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from lca_data_interface import NexusSession

from ecosemantic.databases import command
from ecosemantic.databases.bafu.build import Built, build
from ecosemantic.databases.bafu.download import Downloads, Terms, download, translating
from ecosemantic.databases.bafu.probe import Probe, probe
from ecosemantic.databases.bafu.profile import RELEASES, read_profile, recorded
from ecosemantic.databases.bafu.validate import Counted, record, validate
from ecosemantic.databases.command import Command


def _download(args: argparse.Namespace) -> dict[str, object] | Terms:
    """Fetch a release's packs through Nexus and answer each file's path and the hash the profile
    pins; while the terms are not accepted, answer the licence file and the citation instead."""
    profile = read_profile(args.version)
    with translating(), NexusSession.from_environment(base=profile.server) as session:
        fetched = download(profile, session, accept_terms=args.accept_terms, results=args.results)
    if isinstance(fetched, Terms):
        return fetched
    return {
        "inventory": {"path": str(fetched.inventory), "sha256": profile.inventory.sha256},
        "results": (
            None
            if fetched.results is None
            else {"path": str(fetched.results), "sha256": profile.results.sha256}
        ),
        "licence": str(fetched.licence),
        "citation": fetched.citation,
    }


def _probe(args: argparse.Namespace) -> Probe:
    """Read a zolca and answer what it holds and what the core would not take of it."""
    return probe(Path(args.zolca))


def _fetched(version: str) -> Path:
    """The zolca a release's profile pins, fetched through Nexus with the pack's terms accepted, so
    the answer is always the downloaded file."""
    profile = read_profile(version)
    with translating(), NexusSession.from_environment(base=profile.server) as session:
        fetched = cast(Downloads, download(profile, session, accept_terms=True, results=False))
    return fetched.inventory


def _build(args: argparse.Namespace) -> Built:
    """Build the zolca given, or the one the release's profile pins, into one bundle under
    `--out`."""
    zolca = Path(args.zolca) if args.zolca is not None else _fetched(args.version)
    return build(zolca, version=args.version, out_dir=Path(args.out))


def _validate(args: argparse.Namespace) -> Counted:
    """Compare a bundle with its release's workbook and the release's two lists, record the run
    when asked, and answer the differences counted by column."""
    profile = read_profile(args.version)
    validation = validate(
        Path(args.bundle),
        results=Path(args.results),
        profile=profile,
        unlinked=recorded(profile.unlinked),
        differences=recorded(profile.differences),
        compiled=Path(args.compiled) if args.compiled is not None else None,
    )
    if args.record:
        record(profile, validation, directory=RELEASES)
    return validation.counted()


def _code(answer: object) -> int:
    """2 for the answer that asks for the pack's terms to be accepted, 1 for a validation that
    found a mismatch, and 0 for an answer that stands."""
    if isinstance(answer, Terms):
        return 2
    return 1 if isinstance(answer, Counted) and bool(answer.mismatches) else 0


COMMANDS: dict[str, Command] = {
    "download": Command("Fetch a release's pinned packs from Nexus.", _download),
    "probe": Command("Read a zolca and list what it holds.", _probe),
    "build": Command("Write a release's bundle and import it.", _build),
    "validate": Command("Compare a bundle with its release's workbook.", _validate),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecosemantic-databases bafu",
        description="Build a native EcoSemantic bundle from a BAFU release.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, each in COMMANDS.items():
        sub = subcommands.add_parser(name, help=each.help)
        if name == "download":
            sub.add_argument("version")
            sub.add_argument("--accept-terms", action="store_true")
            sub.add_argument("--results", action="store_true")
        elif name == "probe":
            sub.add_argument("zolca")
        elif name == "build":
            sub.add_argument("version")
            sub.add_argument("--out", required=True)
            sub.add_argument("--zolca")
        elif name == "validate":
            sub.add_argument("version")
            sub.add_argument("--bundle", required=True)
            sub.add_argument("--results", required=True)
            sub.add_argument("--compiled")
            sub.add_argument("--record", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command; 0 on success, 1 on a typed error or a validation that found a mismatch,
    and 2 when the terms are not accepted."""
    return command.main(_parser(), COMMANDS, argv, code=_code)
