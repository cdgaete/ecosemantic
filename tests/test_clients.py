from __future__ import annotations

import json
import sys
import sysconfig
from pathlib import Path

import pytest

from ecosemantic.cli import main
from ecosemantic.cli.clients import SERVER, found, installed_command
from ecosemantic.local import default_directories
from tests.fixture_data import FIXTURE_DB


def connected(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main([*argv, "--json"]) == 0, capsys.readouterr().err
    return json.loads(capsys.readouterr().out)


def refused(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main([*argv, "--json"]) == 1
    return json.loads(capsys.readouterr().err)


def on(platform: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ecosemantic.cli.clients.sys.platform", platform)


def test_the_installed_command_is_the_one_beside_this_interpreter() -> None:
    name = "ecosemantic.exe" if sys.platform == "win32" else "ecosemantic"
    assert installed_command() == Path(sysconfig.get_path("scripts")) / name


def test_found_names_each_client_whose_folder_exists(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    on("darwin", monkeypatch)
    (home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
    assert found() == ["claude-desktop"]
    on("linux", monkeypatch)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert found() == []
    (home / ".config" / "Claude").mkdir(parents=True)
    assert found() == ["claude-desktop"]


def test_claude_desktop_on_macos_gains_the_server_beside_the_ones_it_holds(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    on("darwin", monkeypatch)
    folder = home / "Library" / "Application Support" / "Claude"
    folder.mkdir(parents=True)
    config = folder / "claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    answer = connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert answer == {
        "client": "claude-desktop",
        "path": str(config),
        "server": SERVER,
        "command": str(command),
        "replaced": False,
    }
    held = json.loads(config.read_text())
    assert held["theme"] == "dark" and held["mcpServers"]["other"] == {"command": "x"}
    assert held["mcpServers"][SERVER] == {"command": str(command), "args": ["serve"]}
    # json escapes every backslash of the path, and reading it answers the path itself
    assert "\\\\" in config.read_text() and json.dumps(str(command)) in config.read_text()


def test_claude_desktop_on_windows_is_kept_under_appdata(
    home: Path,
    command: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on("win32", monkeypatch)
    roaming = tmp_path / "Roaming"
    (roaming / "Claude").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(roaming))
    answer = connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    config = roaming / "Claude" / "claude_desktop_config.json"
    assert answer["path"] == str(config)
    assert json.loads(config.read_text()) == {
        "mcpServers": {SERVER: {"command": str(command), "args": ["serve"]}}
    }


def test_claude_desktop_on_linux_is_kept_under_the_config_home(
    home: Path,
    command: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on("linux", monkeypatch)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Anthropic's Debian package, Claude Desktop 3.6556.1, keeps it under ~/.config/Claude
    folder = home / ".config" / "Claude"
    folder.mkdir(parents=True)
    config = folder / "claude_desktop_config.json"
    config.write_text(
        json.dumps({"mcpServers": {"PyPSA MCP": {"command": "uv"}}, "preferences": {"a": 1}})
    )
    answer = connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert answer["path"] == str(config)
    held = json.loads(config.read_text())
    assert held["preferences"] == {"a": 1}
    assert held["mcpServers"]["PyPSA MCP"] == {"command": "uv"}
    assert held["mcpServers"][SERVER] == {"command": str(command), "args": ["serve"]}
    # Electron's appData on Linux is $XDG_CONFIG_HOME when it is set
    configured = tmp_path / "configured"
    (configured / "Claude").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(configured))
    answer = connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert answer["path"] == str(configured / "Claude" / "claude_desktop_config.json")


def linux_config(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The file Claude Desktop keeps on Linux, under a home with no `XDG_CONFIG_HOME`."""
    on("linux", monkeypatch)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (home / ".config" / "Claude").mkdir(parents=True)
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def test_an_entry_on_linux_carries_the_display_it_was_connected_under(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = linux_config(home, monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    written = json.loads(config.read_text())["mcpServers"][SERVER]
    assert written == {"command": str(command), "args": ["serve"], "env": {"DISPLAY": ":0"}}
    assert list(written) == ["command", "args", "env"]
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert json.loads(config.read_text())["mcpServers"][SERVER]["env"] == {
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
    }


def test_an_entry_on_linux_without_a_display_carries_no_env(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = linux_config(home, monkeypatch)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert json.loads(config.read_text())["mcpServers"][SERVER] == {
        "command": str(command),
        "args": ["serve"],
    }


def test_an_empty_display_is_not_written(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = linux_config(home, monkeypatch)
    monkeypatch.setenv("DISPLAY", "")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    written = json.loads(config.read_text())["mcpServers"][SERVER]
    assert written == {"command": str(command), "args": ["serve"]}


def test_an_entry_on_macos_carries_no_env(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    on("darwin", monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    folder = home / "Library" / "Application Support" / "Claude"
    folder.mkdir(parents=True)
    config = folder / "claude_desktop_config.json"
    connected(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert json.loads(config.read_text())["mcpServers"][SERVER] == {
        "command": str(command),
        "args": ["serve"],
    }


def test_claude_desktop_on_another_platform_is_refused_naming_it(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    on("freebsd14", monkeypatch)
    payload = refused(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert payload["error"] == "not_supported" and "freebsd14" in payload["message"]


def test_a_client_that_is_not_installed_is_refused_naming_its_folder(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    on("darwin", monkeypatch)
    payload = refused(["connect", "claude-desktop", "--command", str(command)], capsys)
    assert payload["error"] == "unavailable"
    assert str(home / "Library" / "Application Support" / "Claude") in payload["message"]


def test_cursor_gains_a_typed_stdio_entry_in_its_home_folder(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".cursor").mkdir()
    answer = connected(["connect", "cursor", "--command", str(command)], capsys)
    config = home / ".cursor" / "mcp.json"
    assert answer["path"] == str(config)
    assert json.loads(config.read_text()) == {
        "mcpServers": {SERVER: {"type": "stdio", "command": str(command), "args": ["serve"]}}
    }
    again = connected(["connect", "cursor", "--command", str(command)], capsys)
    assert again["replaced"] is True


def test_vs_code_is_configured_for_the_workspace_it_names(
    home: Path, command: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    answer = connected(
        ["connect", "vscode", "--workspace", str(folder), "--command", str(command)], capsys
    )
    config = folder / ".vscode" / "mcp.json"
    assert answer["path"] == str(config)
    assert json.loads(config.read_text()) == {
        "servers": {SERVER: {"type": "stdio", "command": str(command), "args": ["serve"]}}
    }


def test_vs_code_without_a_workspace_is_refused(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = refused(["connect", "vscode", "--command", str(command)], capsys)
    assert payload["error"] == "invalid" and "--workspace" in payload["message"]


def test_a_malformed_configuration_is_refused_and_left_as_it_was(
    home: Path, command: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".cursor").mkdir()
    config = home / ".cursor" / "mcp.json"
    config.write_text('{"mcpServers": {')
    payload = refused(["connect", "cursor", "--command", str(command)], capsys)
    assert payload["error"] == "invalid" and str(config) in payload["message"]
    assert config.read_text() == '{"mcpServers": {'
    config.write_text('{"mcpServers": []}')
    payload = refused(["connect", "cursor", "--command", str(command)], capsys)
    assert payload["error"] == "invalid" and "mcpServers" in payload["message"]


def test_a_command_that_does_not_exist_is_refused(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".cursor").mkdir()
    payload = refused(["connect", "cursor", "--command", str(tmp_path / "nothing")], capsys)
    assert payload["error"] == "unavailable" and "nothing" in payload["message"]


def test_doctor_reports_an_install_with_nothing_set_up(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = connected(["doctor"], capsys)
    assert report["python"]["version"].count(".") == 2
    assert report["ecosemantic"]
    assert isinstance(report["solver"]["pardiso"], bool)
    data, _ = default_directories()
    assert report["directories"]["data"] == {"path": str(data), "exists": False}
    assert report["databases"] == []
    assert isinstance(report["view"]["port"], int) and isinstance(report["view"]["free"], bool)
    assert report["clients"]["cursor"] == {
        "path": str(home / ".cursor" / "mcp.json"),
        "present": False,
    }
    # doctor makes no directory it reports on
    assert not data.exists()


def test_doctor_reports_the_databases_and_a_configured_client(
    home: Path,
    bundle_dir: Path,
    command: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (home / ".cursor").mkdir()
    connected(["connect", "cursor", "--command", str(command)], capsys)
    report = connected(["doctor", "--data-dir", str(bundle_dir)], capsys)
    assert FIXTURE_DB in report["databases"]
    assert report["directories"]["data"] == {"path": str(bundle_dir), "exists": True}
    assert report["clients"]["cursor"] == {
        "path": str(home / ".cursor" / "mcp.json"),
        "present": True,
        "command": str(command),
        "command_exists": True,
    }
