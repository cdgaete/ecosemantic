"""The yes that sends a country is one a person types at a terminal, asked by name."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ecosemantic import cli, telemetry
from ecosemantic.cli import main


class Terminal(io.StringIO):
    """A stream that says it is a terminal."""

    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr(telemetry, "country_here", lambda environ: "CL", raising=False)


def typed(monkeypatch: pytest.MonkeyPatch, text: str) -> Terminal:
    """A terminal at which the person types the text; what is asked of them."""
    asked = Terminal()
    monkeypatch.setattr("sys.stdin", Terminal(text))
    monkeypatch.setattr("sys.stderr", asked)
    return asked


def answer(data: Path) -> object:
    path = data / telemetry.FILE
    return json.loads(path.read_text(encoding="utf-8")).get("country") if path.exists() else None


def turned_on(data: Path, *more: str) -> int:
    return main(["telemetry", "on", "--data-dir", str(data), *more])


@pytest.mark.parametrize("text", ["y\n", "yes\n", " YES \n"])
def test_a_typed_yes_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    asked = typed(monkeypatch, text)
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) == "yes"
    assert "CL" in asked.getvalue() and "[y/N]" in asked.getvalue()


@pytest.mark.parametrize("text", ["\n", "n\n", "no\n", "CL\n", "sure\n"])
def test_any_other_answer_is_a_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    (tmp_path / telemetry.FILE).write_text('{"country": "yes"}', encoding="utf-8")
    typed(monkeypatch, text)
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) == "no"


def test_input_that_ends_unanswered_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    typed(monkeypatch, "")
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) is None


@pytest.mark.parametrize(
    ("stdin", "stderr"),
    [(io.StringIO, Terminal), (Terminal, io.StringIO), (None, Terminal), (Terminal, None)],
)
def test_a_script_turning_telemetry_on_gives_no_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdin: type | None, stderr: type | None
) -> None:
    monkeypatch.setattr("sys.stdin", None if stdin is None else stdin("y\n"))
    monkeypatch.setattr("sys.stderr", None if stderr is None else stderr())
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) is None


def test_json_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = typed(monkeypatch, "y\n")
    assert turned_on(tmp_path, "--json") == 0
    assert json.loads(capsys.readouterr().out)["country_answer"] is None
    assert asked.getvalue() == ""


@pytest.mark.parametrize("argv", [[], ["off"]])
def test_showing_or_turning_off_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    asked = typed(monkeypatch, "y\n")
    assert main(["telemetry", *argv, "--data-dir", str(tmp_path)]) == 0
    assert answer(tmp_path) is None
    assert asked.getvalue() == ""


def test_a_variable_that_turns_telemetry_off_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    asked = typed(monkeypatch, "y\n")
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) is None
    assert asked.getvalue() == ""


def test_no_country_found_asks_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "country_here", lambda environ: None, raising=False)
    asked = typed(monkeypatch, "y\n")
    assert turned_on(tmp_path) == 0
    assert answer(tmp_path) is None
    assert asked.getvalue() == ""


@pytest.mark.parametrize(
    ("held", "shown"),
    [
        ({"country": "yes"}, "CL, sent"),
        ({"country": "no"}, "CL, not sent"),
        ({"choice": "on"}, "CL, not sent"),
        ({"choice": "off", "country": "yes"}, "CL, not sent"),
    ],
)
def test_telemetry_shows_the_country_and_whether_it_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held: dict[str, str], shown: str
) -> None:
    (tmp_path / telemetry.FILE).write_text(json.dumps(held), encoding="utf-8")
    assert main(["telemetry", "--data-dir", str(tmp_path)]) == 0
    assert shown in capsys.readouterr().out


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An install with one chatbot to connect, its data under the test's own directory."""
    monkeypatch.setattr(cli, "found", lambda: ["claude-desktop"])
    monkeypatch.setattr(cli, "connect", lambda client, workspace, command: {})
    monkeypatch.setattr(cli, "directories", lambda data, systems: (tmp_path, tmp_path))
    monkeypatch.setattr(cli, "init_text", lambda answer: "done")
    return tmp_path


def test_init_asks_at_a_terminal(installed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = typed(monkeypatch, "y\n")
    assert main(["init"]) == 0
    assert answer(installed) == "yes"
    assert "[y/N]" in asked.getvalue()


@pytest.mark.parametrize("held", ["yes", "no"])
def test_init_asks_once(installed: Path, monkeypatch: pytest.MonkeyPatch, held: str) -> None:
    (installed / telemetry.FILE).write_text(json.dumps({"country": held}), encoding="utf-8")
    asked = typed(monkeypatch, "y\n")
    assert main(["init"]) == 0
    assert answer(installed) == held
    assert asked.getvalue() == ""


def test_init_in_a_script_gives_no_yes(installed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    assert main(["init"]) == 0
    assert answer(installed) is None


def test_init_with_a_broken_telemetry_file_still_connects(
    installed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (installed / telemetry.FILE).write_text("{", encoding="utf-8")
    asked = typed(monkeypatch, "y\n")
    assert main(["init"]) == 0
    assert asked.getvalue() == ""


def test_init_json_asks_nothing(
    installed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = typed(monkeypatch, "y\n")
    assert main(["init", "--json"]) == 0
    assert answer(installed) is None
    assert asked.getvalue() == ""
    assert json.loads(capsys.readouterr().out)["next"]
