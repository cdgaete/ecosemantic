"""The command line: the subcommands a USLCI source answers."""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

from lca_data_interface import CommonsServer

from ecosemantic.databases import command
from ecosemantic.databases.command import Command
from ecosemantic.databases.uslci.build import build
from ecosemantic.databases.uslci.download import download
from ecosemantic.databases.uslci.probe import probe
from ecosemantic.databases.uslci.profile import read_profile, recorded
from ecosemantic.databases.uslci.validate import Validation, record, validate
from ecosemantic.errors import Invalid


def _download(args: argparse.Namespace) -> dict[str, object]:
    """Fetch a release's pinned files and answer each one's path and the hash the profile pins."""
    profile = read_profile(args.version)
    files = download(profile, CommonsServer(profile.server))
    return {
        "inventory": {"path": str(files.inventory), "sha256": profile.inventory.sha256},
        "methods": [
            {"path": str(path), "sha256": pin.sha256}
            for path, pin in zip(files.methods, profile.methods, strict=True)
        ],
        "bridged": [
            {"path": str(path), "sha256": pin.sha256}
            for path, pin in zip(files.bridged, profile.bridged, strict=True)
        ],
    }


def _build(args: argparse.Namespace) -> dict[str, object]:
    """Build a release into one bundle under --out, from its profile's downloads or given files."""
    if (args.inventory is None) != (args.method is None) or (
        args.bridged is not None and args.inventory is None
    ):
        raise Invalid("--inventory, --method and --bridged name a release's files together")
    if args.inventory is not None:
        inventory, methods, bridged = args.inventory, tuple(args.method), tuple(args.bridged or ())
    else:
        profile = read_profile(args.version)
        files = download(profile, CommonsServer(profile.server))
        inventory, methods, bridged = files.inventory, files.methods, files.bridged
    built = build(inventory, methods, version=args.version, out_dir=args.out, bridged=bridged)
    return {**dataclasses.asdict(built), "bundle": str(built.bundle)}


def _probe(args: argparse.Namespace) -> dict[str, object]:
    """Read a release with its bridged repositories and its methods and answer what a build of them
    holds and cannot take."""
    return dataclasses.asdict(
        probe(args.inventory, args.methods, bridged=tuple(args.bridged or ()))
    )


def _validate(args: argparse.Namespace) -> Validation:
    """Compare a bundle with the independent computation's scores and the profile's two lists."""
    profile = read_profile(args.version)
    validation = validate(
        args.bundle,
        independent=args.independent,
        built_left_out=args.bundle.with_name(f"left-out-{args.version}.csv"),
        unlinked=recorded(profile.unlinked),
        left_out=recorded(profile.left_out),
        tolerance=profile.tolerance,
        compiled=args.compiled,
    )
    if args.record and not validation.mismatches:
        record(profile, validation)
    return validation


COMMANDS: dict[str, Command] = {
    "download": Command("Fetch a release's pinned files.", _download),
    "probe": Command("List what a release and its methods hold.", _probe),
    "build": Command("Write a release and its methods as one bundle.", _build),
    "validate": Command("Compare a bundle with the independent scores.", _validate),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecosemantic-databases uslci",
        description="Build a native EcoSemantic bundle from a USLCI release.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, each in COMMANDS.items():
        sub = subcommands.add_parser(name, help=each.help)
        if name == "download":
            sub.add_argument("version")
        if name == "probe":
            sub.add_argument("inventory", type=Path)
            sub.add_argument("methods", type=Path, nargs="+")
            sub.add_argument("--bridged", type=Path, nargs="+", default=None)
        if name == "build":
            sub.add_argument("version")
            sub.add_argument("--out", required=True, type=Path)
            sub.add_argument("--inventory", type=Path, default=None)
            sub.add_argument("--method", type=Path, nargs="+", default=None)
            sub.add_argument("--bridged", type=Path, nargs="+", default=None)
        if name == "validate":
            sub.add_argument("version")
            sub.add_argument("--bundle", required=True, type=Path)
            sub.add_argument("--independent", required=True, type=Path)
            sub.add_argument("--compiled", type=Path, default=None)
            sub.add_argument("--record", action="store_true")
    return parser


def _code(answer: object) -> int:
    """1 for a validation that found a mismatch, and 0 otherwise."""
    return 1 if isinstance(answer, Validation) and bool(answer.mismatches) else 0


def main(argv: list[str] | None = None) -> int:
    """Run one command; 0 on success, and 1 on a typed error or a validation that found a
    mismatch."""
    return command.main(_parser(), COMMANDS, argv, code=_code)
