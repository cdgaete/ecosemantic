"""The core as a module: `python -m ecosemantic …` answers as the installed command does."""

from __future__ import annotations

import sys

from ecosemantic.console import main

if __name__ == "__main__":
    sys.exit(main())
