"""The fixture's release served by a stub Collaboration Server, with the profile that pins it and
the two lists it records, for the source's preparation and the command that runs it."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from lca_data_interface import Downloaded, Release

from ecosemantic.databases.lists import (
    LeftOutRow,
    UnlinkedRow,
    write_left_out,
    write_unlinked,
)
from ecosemantic.databases.uslci.profile import Pin, Profile
from tests.databases.uslci_fixture import (
    EXPECTED,
    FLOW_NAMES,
    INVENTORY_NAME,
    METHOD_NAME,
    PROCESS_IDS,
    UNLINKED_CATEGORY,
    _flow_id,
    write_inventory,
    write_method,
)

VERSION = "1.2026-09.0"
INVENTORY_GROUP = "National_Renewable_Energy_Laboratory"
INVENTORY_NAME_ON_SERVER = "USLCI_Database_Public"
INVENTORY_COMMIT = "a" * 40
METHOD_GROUP = "Federal_LCA_Commons"
METHOD_NAME_ON_SERVER = "IPCC_GWP"
METHOD_COMMIT = "b" * 40


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class StubCommons:
    """A Collaboration Server serving the files a test wrote, by group, name and commit."""

    files: dict[tuple[str, str, str], Path]

    def releases(self, group: str, name: str) -> list[Release]:
        return [
            Release(version=VERSION, commit=commit, released_at=datetime(2026, 9, 1, tzinfo=UTC))
            for served_group, served_name, commit in self.files
            if (served_group, served_name) == (group, name)
        ]

    def download(self, group: str, name: str, commit: str) -> Downloaded:
        path = self.files[(group, name, commit)]
        return Downloaded(path=path, size=path.stat().st_size, sha256=_digest(path))


def unlinked_rows() -> tuple[UnlinkedRow, ...]:
    """The unlinked inputs the build leaves, from the fixture's own names, in the order the list is
    read in."""
    rows = tuple(
        UnlinkedRow(
            process_id=PROCESS_IDS[row["process"]],
            process_name=row["process"],
            flow_id=_flow_id(row["flow"]),
            flow_name=FLOW_NAMES[row["flow"]],
            flow_category=UNLINKED_CATEGORY,
            provider_id=None,
        )
        for row in EXPECTED["unlinked"]
    )
    return tuple(sorted(rows, key=lambda row: row.key))


def left_out_rows() -> tuple[LeftOutRow, ...]:
    """The exchanges the build leaves out, keyed by their own ids."""
    return tuple(
        LeftOutRow(
            process_id=PROCESS_IDS[row["process"]],
            process_name=row["process"],
            exchange_id=row["exchange"],
            flow_id=_flow_id(row["flow"]),
            flow_name=FLOW_NAMES[row["flow"]],
            what=row["what"],
            reason=row["reason"],
        )
        for row in EXPECTED["left_out"]
    )


def fixture_release(
    tmp_path: Path, *, drop_unlinked: bool = False, drop_left_out: bool = False
) -> tuple[StubCommons, Profile, Path]:
    """The fixture's two packages served by a stub Collaboration Server, a profile pinning the
    hashes it serves, and a profiles directory recording that profile and the fixture's two lists,
    one row shorter when asked."""
    server = StubCommons(
        {
            (INVENTORY_GROUP, INVENTORY_NAME_ON_SERVER, INVENTORY_COMMIT): write_inventory(
                tmp_path / INVENTORY_NAME
            ),
            (METHOD_GROUP, METHOD_NAME_ON_SERVER, METHOD_COMMIT): write_method(
                tmp_path / METHOD_NAME
            ),
        }
    )
    profile = Profile(
        version=VERSION,
        server="https://www.lcacommons.gov/lca-collaboration",
        inventory=Pin(
            repository=f"{INVENTORY_GROUP}/{INVENTORY_NAME_ON_SERVER}",
            commit=INVENTORY_COMMIT,
            sha256=_digest(
                server.files[(INVENTORY_GROUP, INVENTORY_NAME_ON_SERVER, INVENTORY_COMMIT)]
            ),
        ),
        methods=(
            Pin(
                repository=f"{METHOD_GROUP}/{METHOD_NAME_ON_SERVER}",
                release="1.2026-09.2",
                commit=METHOD_COMMIT,
                sha256=_digest(server.files[(METHOD_GROUP, METHOD_NAME_ON_SERVER, METHOD_COMMIT)]),
            ),
        ),
        unlinked=f"unlinked-{VERSION}.csv",
        left_out=f"left-out-{VERSION}.csv",
    )
    released = tmp_path / "releases"
    released.mkdir()
    (released / f"{VERSION}.yaml").write_text(
        yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    unlinked, left_out = unlinked_rows(), left_out_rows()
    write_unlinked(released / profile.unlinked, unlinked[1:] if drop_unlinked else unlinked)
    write_left_out(released / profile.left_out, left_out[1:] if drop_left_out else left_out)
    return server, profile, released
