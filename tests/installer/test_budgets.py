from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePath, PureWindowsPath

import lca_data_interface.commons
import lca_data_interface.nexus
import pytest
from lca_data_interface import CommonsServer, NexusSession, Pack, PackFile, PackVersion

from ecosemantic.backends.filesystem.activity import activity_file
from ecosemantic.backends.filesystem.installs import INSTALL_FILE, install_dir, uploads_dir
from ecosemantic.backends.filesystem.run_folder import (
    HEARTBEAT_FILE,
    LOG_FILE,
    RECORD_FILE,
    run_dir,
)
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.store import (
    DATABASES_DIR,
    build_dir,
    migrated_name,
    served_build,
)
from ecosemantic.databases.bafu import profile as bafu_profile
from ecosemantic.databases.ecoinvent import profile as ecoinvent_profile
from ecosemantic.databases.uslci import profile as uslci_profile
from ecosemantic.databases.uslci.download import _split
from ecosemantic.installs.sources import downloads_in
from ecosemantic.local import build_context
from ecosemantic.model.refs import slug
from ecosemantic.package.background import read_background
from ecosemantic.ports.types import checked_agent
from ecosemantic.serve import STOP_NONCE_FILE, YIELD_NONCE_FILE, nonce_path, token_for
from ecosemantic.view.installs import upload_path
from scripts.payload import longest_path
from tests.conftest import fixture_system
from tests.engine_fixture import fixture_bundle
from tests.fixture_data import FIXTURE_DB

REPOSITORY = Path(__file__).resolve().parents[2]
BUDGETS = json.loads((REPOSITORY / "installer" / "budgets.json").read_text(encoding="utf-8"))
# the names the BAFU release's files land as: its terms and its inventory archive
BAFU_LICENCE = "BAFU-20XY Terms of Use_EN_openLCA.pdf"
BAFU_INVENTORY = "BAFU-2026 v1.1 openLCA.zolca"
COMMONS_SERVED = "{group}-{name}.zip"


@dataclass
class Answered:
    """One answer a download client receives: the body and the headers that name it."""

    body: bytes
    headers: dict[str, str]
    status_code: int = 200

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    @property
    def raw(self) -> Raw:
        return Raw()

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start : start + chunk_size]


@dataclass
class Raw:
    """The urllib3 layer the client turns length enforcement off on."""

    enforce_content_length: bool = True


class Served:
    """A download client's session: the call that prepares a file answers a token, and the call
    that serves the file names it as the server does."""

    def __init__(self, name: str) -> None:
        self.name = name

    def request(self, method: str, url: str, json: object = None, stream: bool = False) -> Answered:
        if "/prepare/" in url:
            return Answered(b"token", {})
        return Answered(
            b"x",
            {
                "Content-Length": "1",
                "Content-Disposition": f"attachment; filename={self.name}",
            },
        )


def commons_downloads_of(data: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every file the Collaboration Server's cache holds for the releases the core profiles, each
    path from the client that writes it, and the `.part` it writes it under first."""
    paths: list[Path] = []
    with downloads_in(data):
        for version in uslci_profile.versions():
            profile = uslci_profile.read_profile(version)
            for pin in (profile.inventory, *profile.methods, *profile.bridged):
                group, name = _split(pin.repository)
                monkeypatch.setattr(
                    lca_data_interface.commons,
                    "new_session",
                    partial(Served, COMMONS_SERVED.format(group=group, name=name)),
                )
                downloaded = CommonsServer(profile.server).download(group, name, pin.commit)
                paths.append(downloaded.path)
                # fetch writes the body under `<name>.part` and renames it when the length holds
                paths.append(downloaded.path.with_name(f"{downloaded.path.name}.part"))
    return paths


def nexus_downloads_of(data: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every file openLCA Nexus's cache holds for the BAFU releases the core profiles, each path
    from the session that writes it, and the `.part` it writes it under first: the release's terms
    and its inventory archive. These two are what an install fetches; `prepare` in
    `ecosemantic.databases.bafu.setup` downloads with `results=False`, so no results pack lands
    under either folder."""
    paths: list[Path] = []
    with downloads_in(data):
        for version in bafu_profile.versions():
            profile = bafu_profile.read_profile(version)
            pinned = profile.inventory
            pack = Pack(
                uuid=pinned.pack,
                name=version,
                licence_file=1,
                versions=(
                    PackVersion(
                        number=pinned.version,
                        release_note=None,
                        files=(PackFile(datafile_id=1, file_format=pinned.format),),
                    ),
                ),
            )
            monkeypatch.setattr(
                lca_data_interface.nexus, "new_session", partial(Served, BAFU_LICENCE)
            )
            licence = NexusSession("account", "password", base="https://nexus.test").licence(pack)
            paths.append(licence)
            # fetch writes the body under `<name>.part` and renames it when the length holds
            paths.append(licence.with_name(f"{licence.name}.part"))
            monkeypatch.setattr(
                lca_data_interface.nexus, "new_session", partial(Served, BAFU_INVENTORY)
            )
            downloaded = NexusSession("account", "password", base="https://nexus.test").download(
                pack,
                version=pinned.version,
                file_format=pinned.format,
                accept_licence=True,
            )
            paths.append(downloaded.path)
            # fetch writes the body under `<name>.part` and renames it when the length holds
            paths.append(downloaded.path.with_name(f"{downloaded.path.name}.part"))
    return paths


EXTENDED = "\\\\?\\"
EXTENDED_UNC = "\\\\?\\UNC\\"


def ordinary(path: PurePath) -> PurePath:
    """The path as the person's own folder spells it. On Windows the library answers the cache's
    extended-length form — `lca_data_interface.cache.on_disk` hands its callers a path beginning
    with the extended prefix, which the 260-character limit does not bind — and the budget is
    measured on the ordinary form, which is what a person's folder and that limit count."""
    held = str(path)
    if held.startswith(EXTENDED_UNC):
        return type(path)("\\\\" + held[len(EXTENDED_UNC) :])
    if held.startswith(EXTENDED):
        return type(path)(held[len(EXTENDED) :])
    return path


def test_the_extended_length_form_reads_as_the_folder_a_person_sees() -> None:
    r"""Windows answers an extended-length path for what the library opened — a drive path with the
    extended prefix, a share path with `UNC` after it — and the budget counts the ordinary spelling,
    so each is read back as a person types it."""
    extended = PureWindowsPath("\\\\?\\C:\\Users\\person\\databases\\a.zip")
    assert ordinary(extended) == PureWindowsPath("C:\\Users\\person\\databases\\a.zip")
    share = PureWindowsPath("\\\\?\\UNC\\server\\share\\databases\\a.zip")
    assert ordinary(share) == PureWindowsPath("\\\\server\\share\\databases\\a.zip")
    plain = PureWindowsPath("C:\\Users\\person\\databases")
    assert ordinary(plain) == plain


def longest_among(root: Path, paths: list[Path]) -> tuple[int, Path]:
    """The longest of these paths beneath root and the longest path the tree already holds."""
    measured = [(len(ordinary(path).relative_to(root).as_posix()), path) for path in paths]
    relative, length = longest_path(root)
    measured.append((length, root / relative))
    return max(measured, key=lambda one: one[0])


def database_names() -> list[tuple[str, str, str]]:
    """Every database name the core's profiles produce, each with the version and the system model
    it installs under: ecoinvent's, USLCI's and BAFU's."""
    named = [
        (ecoinvent_profile.database_name(version, model), version, model)
        for version, model in ecoinvent_profile.profiled()
    ]
    named += [
        (uslci_profile.database_name(version), version, "unit process")
        for version in uslci_profile.versions()
    ]
    named += [
        (bafu_profile.database_name(version), version, "unit process")
        for version in bafu_profile.versions()
    ]
    return named


def longest_database_name() -> tuple[str, str, str]:
    """The longest of the names every source's profiles produce."""
    return max(database_names(), key=lambda one: len(one[0]))


def test_the_budgets_cover_the_longest_paths_the_engine_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each budget is the longest path the engine writes beneath one folder, computed through the
    code that writes it. Beneath the databases folder: the longest database name every source's
    profiles produce, ecoinvent, USLCI and BAFU (a database named from a person's own zip is not
    bounded); every file each profiled source's download lands as, the Collaboration Server's cache
    and Nexus's, with the `.part` written first; a migrated build; an install record; and an
    uploaded zip. Beneath the models folder: a product system with its versions, its log and its
    lock; a run's record, its worker log and its heartbeat; an agent's activity file; the token; and
    the two nonces."""
    monkeypatch.delenv("LCA_DATA_INTERFACE_CACHE", raising=False)
    named = [one[0] for one in database_names()]
    assert uslci_profile.database_name(uslci_profile.versions()[0]) in named
    assert bafu_profile.database_name(bafu_profile.versions()[0]) in named
    databases_dir = tmp_path / "databases"
    models_dir = tmp_path / "models"
    sources = tmp_path / "sources"
    for directory in (databases_dir, models_dir, sources):
        directory.mkdir()
    name, version, system_model = longest_database_name()
    bundle = fixture_bundle(sources)
    for installed_name, installed_version, installed_model in (
        (FIXTURE_DB, "1", "unit process"),
        (name, version, system_model),
    ):
        imported = read_background(bundle, installed_name, foreground=frozenset())
        install(
            databases_dir,
            imported,
            bundle,
            version=installed_version,
            system_model=installed_model,
        )
    context = build_context(databases_dir, models_dir)
    try:
        asyncio.run(
            context.storage.put_product_system(
                fixture_system().product_system, context.actor, "created"
            )
        )
    finally:
        context.close()
    assert token_for(models_dir, True) is not None
    build_id = served_build(databases_dir / DATABASES_DIR / slug(name, "-"))
    assert build_id is not None
    tail = longest_path(build_dir(databases_dir, name, build_id))[0]
    migrated = build_dir(databases_dir, name, migrated_name("0" * 64)) / tail
    databases_paths = [
        *commons_downloads_of(databases_dir, monkeypatch),
        *nexus_downloads_of(databases_dir, monkeypatch),
        migrated,
        install_dir(databases_dir, uuid.uuid4()) / INSTALL_FILE,
        upload_path(uploads_dir(databases_dir), uuid.uuid4()),
    ]
    assert any(path.name == f"{BAFU_LICENCE}.part" for path in databases_paths)
    assert any(path.name == f"{BAFU_INVENTORY}.part" for path in databases_paths)
    run = run_dir(models_dir, uuid.uuid4())
    models_paths = [
        run / RECORD_FILE,
        run / LOG_FILE,
        run / HEARTBEAT_FILE,
        activity_file(models_dir, checked_agent("a" * 64)),
        nonce_path(models_dir, YIELD_NONCE_FILE),
        nonce_path(models_dir, STOP_NONCE_FILE),
    ]
    assert not any("results" in path.parts for path in models_paths)
    longest_databases = longest_among(databases_dir, databases_paths)
    longest_models = longest_among(models_dir, models_paths)
    assert longest_databases[0] <= BUDGETS["databases"], longest_databases
    assert longest_models[0] <= BUDGETS["models"], longest_models


def test_the_readme_holds_each_folder_to_the_budget_it_was_measured_with() -> None:
    """Every folder keeps one character for the separator and a budget characters beneath it, out
    of the 259 Windows reads, and the README states each folder's remaining length."""
    readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
    assert f"a databases folder of at most {259 - 1 - BUDGETS['databases']} characters" in readme
    assert f"a models folder of at most {259 - 1 - BUDGETS['models']}" in readme
