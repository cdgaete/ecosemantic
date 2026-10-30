"""Install a database from the source it is built from, whichever caller asks: the command line, or
the process that carries an install the page or the chat posted."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from ecoinvent_interface import EcoinventRelease, Settings
from pydantic import JsonValue

from ecosemantic.backends.native.install import Installed, install
from ecosemantic.compute.accounts import missing
from ecosemantic.databases.bafu.download import Terms, download, translating
from ecosemantic.databases.bafu.profile import read_profile as read_bafu
from ecosemantic.databases.bafu.profile import versions as bafu_versions
from ecosemantic.databases.bafu.setup import prepare as prepare_bafu
from ecosemantic.databases.bafu.setup import session as bafu_session
from ecosemantic.databases.ecoinvent.profile import pinned
from ecosemantic.databases.ecoinvent.release import SystemModel
from ecosemantic.databases.ecoinvent.setup import prepare as prepare_ecoinvent
from ecosemantic.databases.uslci.profile import read_profile as read_uslci
from ecosemantic.databases.uslci.profile import versions as uslci_versions
from ecosemantic.databases.uslci.setup import commons
from ecosemantic.databases.uslci.setup import prepare as prepare_uslci
from ecosemantic.errors import Unavailable
from ecosemantic.package.background import Import, read_background
from ecosemantic.ports.types import (
    Account,
    InstallDraft,
    InstallProgress,
    InstallTerms,
    Reporter,
    source_credential,
)

DOWNLOADS = "downloads"
DOWNLOAD_CACHE = "LCA_DATA_INTERFACE_CACHE"


@contextmanager
def downloads_in(data_dir: Path) -> Iterator[None]:
    """Point lca-data-interface's download cache at the data directory's `downloads` folder while
    an install runs, so a release's files land where the person keeps their databases, under a
    root they chose; a cache the person names with the variable is kept."""
    if DOWNLOAD_CACHE in os.environ:
        yield
        return
    os.environ[DOWNLOAD_CACHE] = str(data_dir / DOWNLOADS)
    try:
        yield
    finally:
        del os.environ[DOWNLOAD_CACHE]


def install_source(
    data_dir: Path,
    draft: InstallDraft,
    account: Account | None,
    report: Reporter,
) -> dict[str, JsonValue] | InstallTerms:
    """Install the database a draft names from the source it is built from, reporting each step and
    answering the summary the command prints; a `bafu` draft whose terms are not accepted answers
    them, installing and downloading nothing. A source whose install needs an account and is given
    none is `Unavailable`, naming the variables and the page that supply it."""
    kind = source_credential(draft.source)
    if kind is not None and account is None:
        raise Unavailable(f"{draft.source} needs an account", hint=missing(kind))
    with downloads_in(data_dir):
        if draft.source == "openlca":
            return _openlca(data_dir, draft, report)
        if draft.source == "uslci":
            return _uslci(data_dir, draft, report)
        if draft.source == "ecoinvent":
            return _ecoinvent(data_dir, draft, cast(Account, account), report)
        return _bafu(data_dir, draft, cast(Account, account), report)


def _installed_summary(
    imported: Import,
    installed: Installed,
    unlinked: list[dict[str, JsonValue]],
    dropped: int,
) -> dict[str, JsonValue]:
    """The document an install answers: what it wrote, and the factors of each category the import
    set apart by naming a location."""
    return {
        "database": installed.database.name,
        "elementary_flows": installed.database.elementary_flows,
        "processes": imported.processes,
        "datasets": installed.datasets,
        "flows": installed.flows,
        "methods": installed.methods,
        "unlinked": unlinked,
        "dropped": dropped,
        "directory": str(installed.directory),
        "set_apart": [
            {"method": method.key[1], "category": method.key[2], "factors": method.set_apart}
            for method in imported.methods
            if method.set_apart
        ],
    }


def _openlca(data_dir: Path, draft: InstallDraft, report: Reporter) -> dict[str, JsonValue]:
    """Install the openLCA package a draft names, under the name, version and system model it
    carries, dropping the inputs it asks to drop."""
    package = Path(cast(str, draft.package))
    imported = read_background(package, cast(str, draft.name), foreground=frozenset())
    unlinked = [dataclasses.asdict(row) for row in imported.unlinked]
    dropped = imported.unlinked if draft.drop_unlinked else []
    if draft.drop_unlinked:
        imported = dataclasses.replace(imported, unlinked=[])
    report(InstallProgress(step="installing"))
    installed = install(
        data_dir,
        imported,
        package,
        version=cast(str, draft.version),
        system_model=cast(str, draft.system_model),
        replace=draft.replace,
        dropped=dropped,
    )
    return _installed_summary(imported, installed, unlinked, len(dropped))


def _uslci(data_dir: Path, draft: InstallDraft, report: Reporter) -> dict[str, JsonValue]:
    """Install the USLCI release a profile pins, downloading and building it in a temporary
    directory and holding it to the profile's two lists."""
    profile = read_uslci(draft.version or uslci_versions()[0])
    with tempfile.TemporaryDirectory(prefix="ecosemantic-uslci-") as directory:
        prepared = prepare_uslci(profile, commons(profile.server), Path(directory), report)
        report(InstallProgress(step="installing"))
        installed = install(
            data_dir,
            prepared.imported,
            prepared.bundle,
            version=profile.version,
            system_model="unit process",
            replace=draft.replace,
            dropped=prepared.dropped,
        )
    unlinked = [dataclasses.asdict(row) for row in prepared.unlinked]
    summary = _installed_summary(prepared.imported, installed, unlinked, len(unlinked))
    summary["sources"] = [
        {"repository": pin.repository, "release": pin.release, "commit": pin.commit}
        for pin in prepared.pins
    ]
    summary["notices"] = [dataclasses.asdict(notice) for notice in prepared.notices]
    return summary


def _bafu(
    data_dir: Path, draft: InstallDraft, account: Account, report: Reporter
) -> dict[str, JsonValue] | InstallTerms:
    """Install the BAFU release a profile pins through the Nexus session the account logs in to;
    without the draft's terms accepted, answer the licence file and the citation instead."""
    profile = read_bafu(draft.version or bafu_versions()[0])
    with translating(), bafu_session(profile.server, account) as nexus:
        if not draft.accept_terms:
            return _terms(cast(Terms, download(profile, nexus, accept_terms=False, results=False)))
        with tempfile.TemporaryDirectory(prefix="ecosemantic-bafu-") as directory:
            prepared = prepare_bafu(profile, nexus, Path(directory), report)
            report(InstallProgress(step="installing"))
            installed = install(
                data_dir,
                prepared.imported,
                prepared.bundle,
                version=profile.version,
                system_model="unit process",
                replace=draft.replace,
                dropped=prepared.dropped,
            )
    unlinked = [dataclasses.asdict(row) for row in prepared.unlinked]
    summary = _installed_summary(prepared.imported, installed, unlinked, len(unlinked))
    summary["licence"] = str(prepared.licence)
    summary["citation"] = prepared.citation
    summary["not_applied"] = dataclasses.asdict(prepared.not_applied)
    return summary


def _terms(terms: Terms) -> InstallTerms:
    """The licence file to read and the citation it carries, as an install answers them."""
    return InstallTerms(licence=str(terms.licence), citation=terms.citation)


def _ecoinvent(
    data_dir: Path, draft: InstallDraft, account: Account, report: Reporter
) -> dict[str, JsonValue]:
    """Install the ecoinvent release a profile pins, built and validated in a temporary directory
    with the client the account's values make."""
    profile = pinned(cast(str, draft.version), cast(SystemModel, draft.system_model))
    client = EcoinventRelease(
        Settings(username=account.username, password=account.password.get_secret_value())
    )
    with tempfile.TemporaryDirectory(prefix="ecosemantic-ecoinvent-") as directory:
        prepared = prepare_ecoinvent(
            profile.version, profile.system_model, client, profile, Path(directory), report
        )
        report(InstallProgress(step="installing"))
        installed = install(
            data_dir,
            prepared.imported,
            prepared.bundle,
            version=profile.version,
            system_model=profile.system_model,
            replace=draft.replace,
        )
    return _installed_summary(prepared.imported, installed, [], 0)
