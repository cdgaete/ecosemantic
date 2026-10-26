from __future__ import annotations

from types import ModuleType

import pytest

from ecosemantic.databases.cli import main
from ecosemantic.databases.ecoinvent.profile import RELEASES


def test_the_release_profiles_ship_inside_the_package() -> None:
    assert RELEASES.parent.name == "ecoinvent"
    assert sorted(path.name for path in RELEASES.glob("*.yaml")) == [
        "3.10-cutoff.yaml",
        "3.10.1-cutoff.yaml",
        "3.11-cutoff.yaml",
        "3.12-cutoff.yaml",
    ]


def test_an_unknown_source_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as refused:
        main(["nexus", "build", "1"])
    assert refused.value.code == 2
    assert "ecoinvent" in capsys.readouterr().err


def test_a_source_runs_its_own_command_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as shown:
        main(["ecoinvent", "--help"])
    assert shown.value.code == 0
    assert "ecosemantic-databases ecoinvent" in capsys.readouterr().out


def test_a_source_whose_extra_is_missing_names_the_extra(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def without_the_extra(name: str) -> ModuleType:
        raise ModuleNotFoundError(
            "No module named 'ecoinvent_interface'", name="ecoinvent_interface"
        )

    monkeypatch.setattr("ecosemantic.databases.cli.importlib.import_module", without_the_extra)
    assert main(["ecoinvent", "probe", "3.12", "--system-model", "cutoff"]) == 2
    assert "ecosemantic-databases[ecoinvent]" in capsys.readouterr().err
