"""The command that builds a bundle from one source's own files, the source named first."""

from __future__ import annotations

import argparse
import importlib
import sys

SOURCES = {
    "bafu": "ecosemantic.databases.bafu.cli",
    "ecoinvent": "ecosemantic.databases.ecoinvent.cli",
    "uslci": "ecosemantic.databases.uslci.cli",
}


def main(argv: list[str] | None = None) -> int:
    """Run one source's command; 2 when the source's extra is not installed."""
    parser = argparse.ArgumentParser(
        prog="ecosemantic-databases",
        description="Build a native EcoSemantic bundle from a source database's own files.",
    )
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        source = importlib.import_module(SOURCES[args.source])
    except ModuleNotFoundError as missing:
        print(
            f"{args.source} needs {missing.name}: install ecosemantic-databases[{args.source}]",
            file=sys.stderr,
        )
        return 2
    return source.main(args.arguments)
