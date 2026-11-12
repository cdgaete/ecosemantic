"""The one replace every writer lands a file through, and what a held destination answers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ecosemantic import files
from ecosemantic.bridge.credentials import FileStore
from ecosemantic.errors import Unavailable
from ecosemantic.settings.handover import STOP_NONCE_FILE, asked_with_nonce
from ecosemantic.telemetry import record
from ecosemantic.tray.home import written
from tests.bridge.test_credentials import a_credential


def test_a_held_destination_is_unavailable_and_leaves_no_staged_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def held(source: object, destination: object) -> None:
        raise PermissionError(13, "the file is held by another process")

    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0)
    monkeypatch.setattr(os, "replace", held)
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Unavailable):
        asked_with_nonce(tmp_path, STOP_NONCE_FILE, "http://127.0.0.1:1/stop")
    assert sorted(tmp_path.iterdir()) == before
    with pytest.raises(Unavailable):
        FileStore(tmp_path / "credential.json").save(a_credential())
    assert sorted(tmp_path.iterdir()) == before
    with pytest.raises(Unavailable):
        record({}, tmp_path, False)
    assert sorted(tmp_path.iterdir()) == before
    with pytest.raises(Unavailable):
        written(tmp_path / "tray.pid", "4242\n")
    assert sorted(tmp_path.iterdir()) == before


def test_a_whole_write_leaves_no_sibling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "settings.json"
    files.write_whole(target, b'{"bridge": true}')
    assert target.read_bytes() == b'{"bridge": true}'
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]

    def held(source: object, destination: object) -> None:
        raise PermissionError(13, "the file is held by another process")

    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0)
    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(Unavailable):
        files.write_whole(target, b'{"bridge": false}')
    assert target.read_bytes() == b'{"bridge": true}'
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]
