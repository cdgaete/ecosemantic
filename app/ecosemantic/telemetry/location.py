"""The country this computer's own settings name: its time zone's, or its region setting's on
Windows. No address is read and nothing is asked over the network."""

from __future__ import annotations

import ctypes
import os
import re
import sys
from collections.abc import Mapping
from functools import cache
from pathlib import Path

ZONES = Path(__file__).parent / "data" / "zone_countries.tab"
LOCALTIME = Path("/etc/localtime")
LINK_HOPS = 8
IN_ZONEINFO = re.compile(r".*zoneinfo[^/]*/(?:posix/|right/)?(.+)")
GEOCLASS_NATION = 16
GEO_ISO2 = 4


@cache
def _countries() -> Mapping[str, str]:
    """Each zone name's country, as the table carried beside this module gives it."""
    lines = ZONES.read_text(encoding="utf-8").splitlines()
    rows = (line.split("\t") for line in lines if not line.startswith("#"))
    return {row[0]: row[1] for row in rows}


def country_of(zone: str) -> str | None:
    """The two-letter country of a zone's own name, or none for a zone of no one country."""
    return _countries().get(zone)


def zone_name(environ: Mapping[str, str], localtime: Path = LOCALTIME) -> str | None:
    """The name of the zone in force: the TZ variable's, else the one the localtime link names. A
    link is read and never resolved to its end, since tzdata links one country's zone to
    another's, and a localtime that is a copy names none."""
    named = environ.get("TZ")
    if named is not None:
        named = named.removeprefix(":")
        if named != str(localtime):
            found = IN_ZONEINFO.fullmatch(named)
            return found.group(1) if found else named
    link = localtime
    for _ in range(LINK_HOPS):
        if not link.is_symlink():
            return None
        target = os.readlink(link).replace(os.sep, "/")
        found = IN_ZONEINFO.fullmatch(target)
        if found:
            return found.group(1)
        link = link.parent / target
    return None


def _region() -> str | None:
    """The two-letter code of Windows' region setting, or none when it names no country."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32")
    place = kernel32.GetUserGeoID(GEOCLASS_NATION)
    written = ctypes.create_unicode_buffer(16)
    if not kernel32.GetGeoInfoW(place, GEO_ISO2, written, len(written), 0):
        return None
    code = written.value
    return code if len(code) == 2 and code.isascii() and code.isupper() else None


def country_here(environ: Mapping[str, str]) -> str | None:
    """The country this computer's settings name, or none; a country is never inferred."""
    if sys.platform == "win32":
        return _region()
    zone = zone_name(environ)
    return None if zone is None else country_of(zone)


def country_source() -> str:
    """The setting this computer's country is read from, as a person is told it."""
    return "region setting" if sys.platform == "win32" else "time zone"
