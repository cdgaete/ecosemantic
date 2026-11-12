"""Fetch a USLCI release's pinned files from a Collaboration Server, refusing a file whose hash is
not the one its profile pins."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lca_data_interface import Downloaded, Release
from lca_data_interface.errors import LcaDataInterfaceError, NotOnServer

from ecosemantic.databases import downloads
from ecosemantic.databases.uslci.profile import Pin, Profile
from ecosemantic.errors import EcoSemanticError, NotFound


class Commons(Protocol):
    """The two calls a download makes on a Collaboration Server; CommonsServer satisfies it and a
    test doubles it."""

    def releases(self, group: str, name: str) -> list[Release]: ...

    def download(self, group: str, name: str, commit: str) -> Downloaded: ...


@dataclass(frozen=True)
class Downloads:
    """The files a download fetched: the inventory, the file of every method a profile pins, and the
    file of every repository its bridges link to."""

    inventory: Path
    methods: tuple[Path, ...]
    bridged: tuple[Path, ...] = ()


def _split(repository: str) -> tuple[str, str]:
    """The group and the name a repository names."""
    group, _, name = repository.partition("/")
    return group, name


def download(profile: Profile, server: Commons) -> Downloads:
    """Fetch the inventory, the repositories its bridges link to and every method at the commits a
    profile pins, refusing a file whose hash is not the one its pin holds."""
    inventory = _fetched(profile.inventory, server=server)
    bridged = tuple(_fetched(pin, server=server) for pin in profile.bridged)
    methods = tuple(_fetched(pin, server=server) for pin in profile.methods)
    return Downloads(inventory=inventory, methods=methods, bridged=bridged)


def _fetched(pin: Pin, *, server: Commons) -> Path:
    """One pinned file, fetched and its SHA-256 compared with the pin's."""
    group, name = _split(pin.repository)
    try:
        downloaded = server.download(group, name, pin.commit)
    except LcaDataInterfaceError as error:
        raise _translated(error, server=server) from error
    return downloads.checked(downloaded, pin.sha256)


def _translated(error: LcaDataInterfaceError, *, server: Commons) -> EcoSemanticError:
    """The core's error for one the client raised: a commit the server does not hold is not found
    and names the commits its repository does release, a repository it does not hold is not found,
    and every other error is the one `downloads.translated` gives it."""
    if not isinstance(error, NotOnServer):
        return downloads.translated(error)
    if error.commit is None:
        return NotFound(f"the server does not hold {error.repository}: {error.detail}")
    released = _released(error.repository, server=server)
    return NotFound(
        f"{error.repository} at commit {error.commit} is not on the server: {error.detail}; "
        f"the commits it releases are {', '.join(released) or 'none'}"
    )


def _released(repository: str, *, server: Commons) -> tuple[str, ...]:
    """The commits a repository releases, each named with its version. A history the server will
    not answer raises the core's error for it, which names no released commits and so asks for
    none: the two calls cannot translate each other without end."""
    group, name = _split(repository)
    try:
        releases = server.releases(group, name)
    except LcaDataInterfaceError as error:
        raise _translated(error, server=server) from error
    return tuple(f"{release.version} at {release.commit}" for release in releases)
