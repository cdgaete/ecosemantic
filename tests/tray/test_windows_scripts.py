"""The Python the Windows tests hand a child interpreter, compiled on every host: a constant there
that Python cannot compile is a child that dies in the job test, which runs on Windows only."""

from __future__ import annotations

import pytest

from tests.tray import test_windows

SCRIPTS = {
    name: value
    for name, value in vars(test_windows).items()
    if name.endswith("_SCRIPT") and isinstance(value, str)
}


def test_the_windows_tests_hold_a_script_for_the_tray_and_one_for_the_launcher() -> None:
    assert "TRAY_SCRIPT" in SCRIPTS and "LAUNCHER_SCRIPT" in SCRIPTS, sorted(SCRIPTS)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_every_script_the_windows_tests_give_a_child_interpreter_compiles(name: str) -> None:
    compile(SCRIPTS[name], f"{name} in tests/tray/test_windows.py", "exec")
