"""What every release built from unit processes holds once it is prepared for an install."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ecosemantic.databases.lists import UnlinkedRow
from ecosemantic.package.background import Import, Unlinked


@dataclass(frozen=True)
class PreparedRelease:
    """A release ready to install: its bundle, the import of it with the inputs no process provides
    left out, the unlinked inputs its profile holds it to, and the records of those inputs the
    install lists as cut off."""

    bundle: Path
    imported: Import
    unlinked: tuple[UnlinkedRow, ...]
    dropped: tuple[Unlinked, ...]
