from __future__ import annotations

import http.server
import os
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ecosemantic.settings.handover import STOP_NONCE_FILE, asked_with_nonce


class Handler(http.server.BaseHTTPRequestHandler):
    """A handover route answering with the body its server names, recording what the systems
    directory held and the mode of each file in it while it answered."""

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        server = self.server
        server.seen.append(sorted(path.name for path in server.folder.iterdir()))
        server.modes.extend(path.stat().st_mode & 0o777 for path in server.folder.iterdir())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(server.body)))
        self.end_headers()
        self.wfile.write(server.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class Server(http.server.HTTPServer):
    """A handover route on a port of its own, answering with this body."""

    body = b""
    folder = Path()
    seen: list[list[str]] = []
    modes: list[int] = []


@contextmanager
def served(folder: Path, body: bytes) -> Iterator[str]:
    """The URL of a handover route on this machine answering with this body."""
    Server.body = body
    Server.folder = folder
    Server.seen = []
    Server.modes = []
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/stop"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def garbage() -> Iterator[str]:
    """The URL of a listener that reads the request and answers what no HTTP client can parse."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def answering() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.recv(65536)
            connection.sendall(b"ECOSEMANTIC NOT HTTP\r\n\r\n")

    thread = threading.Thread(target=answering, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/stop"
    finally:
        listener.close()
        thread.join(timeout=5)


def test_a_listener_that_does_not_speak_http_is_no_answer(tmp_path: Path) -> None:
    with garbage() as url:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, url) is None
    assert list(tmp_path.iterdir()) == []


def test_an_answer_that_is_not_json_is_no_answer(tmp_path: Path) -> None:
    with served(tmp_path, b"<html>another program</html>") as url:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, url) is None
    assert list(tmp_path.iterdir()) == []


def test_an_answer_that_is_not_an_object_is_no_answer(tmp_path: Path) -> None:
    with served(tmp_path, b'["stopped"]') as url:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, url) is None
    assert list(tmp_path.iterdir()) == []


def test_a_write_the_os_refuses_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refusing(source: str, target: str) -> None:
        raise OSError(5, "the file is held by another process")

    monkeypatch.setattr("ecosemantic.settings.handover.os.replace", refusing)
    with pytest.raises(OSError, match="held by another process"):
        asked_with_nonce(tmp_path, STOP_NONCE_FILE, "http://127.0.0.1:1/stop")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="only POSIX carries a file mode")
def test_the_nonce_reaches_the_route_from_a_private_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged: list[tuple[Path, int]] = []
    replacing = os.replace

    def recording(source: str, target: str) -> None:
        staged.append((Path(source), Path(source).stat().st_mode & 0o777))
        replacing(source, target)

    monkeypatch.setattr("ecosemantic.settings.handover.os.replace", recording)
    with served(tmp_path, b'{"stopped": true}') as url:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, url) == {"stopped": True}
    assert Server.seen == [[STOP_NONCE_FILE]]
    assert Server.modes == [0o600]
    assert len(staged) == 1
    written, mode = staged[0]
    assert written.parent == tmp_path
    assert written.name.startswith(f".{STOP_NONCE_FILE}.")
    assert mode == 0o600
    assert list(tmp_path.iterdir()) == []
