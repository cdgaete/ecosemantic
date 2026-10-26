from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.installs import FilesystemInstalls
from ecosemantic.errors import Unavailable
from ecosemantic.installs.supervisor import LocalInstaller
from ecosemantic.local import DATA_DIR, build_context, default_directories


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.delenv(DATA_DIR, raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    return tmp_path


def test_linux_takes_the_xdg_data_home(clean: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(clean / "share"))
    data, systems = default_directories()
    assert data == clean / "share" / "ecosemantic" / "data"
    assert systems == clean / "share" / "ecosemantic" / "systems"
    assert not data.exists() and not systems.exists()


def test_linux_without_the_xdg_data_home_takes_the_home_s_share(
    clean: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    data, systems = default_directories()
    assert data == clean / "home" / ".local" / "share" / "ecosemantic" / "data"
    assert systems == clean / "home" / ".local" / "share" / "ecosemantic" / "systems"


def test_macos_takes_application_support(clean: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    data, systems = default_directories()
    assert data == clean / "home" / "Library" / "Application Support" / "ecosemantic" / "data"
    assert systems.parent == data.parent


def test_windows_takes_the_local_app_data(clean: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(clean / "local"))
    data, systems = default_directories()
    assert data == clean / "local" / "ecosemantic" / "data"
    assert systems == clean / "local" / "ecosemantic" / "systems"


def test_windows_without_the_local_app_data_is_unavailable(
    clean: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(Unavailable, match="LOCALAPPDATA"):
        default_directories()


def test_the_variable_names_the_data_directory(
    clean: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv(DATA_DIR, str(clean / "elsewhere"))
    data, systems = default_directories()
    assert data == clean / "elsewhere"
    assert systems == clean / "home" / ".local" / "share" / "ecosemantic" / "systems"


def test_build_context_holds_the_accounts_the_environment_names(
    bundle_dir: Path, tmp_path: Path
) -> None:
    systems = tmp_path / "systems"
    systems.mkdir()
    context = build_context(
        bundle_dir,
        systems,
        environ={"EI_USERNAME": "me", "EI_PASSWORD": "hunter2", "NEXUS_USERNAME": "only-a-name"},
    )
    try:
        assert set(context.credentials) == {"ecoinvent"}
        account = context.credentials["ecoinvent"]
        assert account.username == "me"
        assert account.password.get_secret_value() == "hunter2"
        assert isinstance(context.installs, FilesystemInstalls)
        assert isinstance(context.installer, LocalInstaller)
    finally:
        context.close()
