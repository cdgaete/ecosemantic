"""The installed command, which keeps stdout for the command's answer while the libraries load."""

from __future__ import annotations

import contextlib
import sys


def main() -> int:
    """Run the command named in argv; what a library prints while it is imported goes to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        from ecosemantic.cli import main as command
    return command()
