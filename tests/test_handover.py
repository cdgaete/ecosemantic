from __future__ import annotations

import http.server
import json
import os
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from ecosemantic.errors import Unavailable
from ecosemantic.serve import stop_route, yield_route
from ecosemantic.settings.handover import (
    LOOPBACK_ADDRESS,
    SERVICE,
    STOP_NONCE_FILE,
    YIELD_NONCE_FILE,
    BridgeHealth,
    Health,
    asked_with_nonce,
    proven,
    read_health,
)


class Handler(http.server.BaseHTTPRequestHandler):
    """A route answering with the body its server names; a POST records what the systems directory
    held and the mode of each file in it while it answered."""

    def do_GET(self) -> None:
        self._answered()

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        server = self.server
        server.seen.append(sorted(path.name for path in server.folder.iterdir()))
        server.modes.extend(path.stat().st_mode & 0o777 for path in server.folder.iterdir())
        self._answered()

    def _answered(self) -> None:
        server = self.server
        self.send_response(server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(server.body)))
        self.end_headers()
        self.wfile.write(server.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class Server(http.server.HTTPServer):
    """A handover route on a port of its own, answering with this body."""

    body = b""
    status = 200
    folder = Path()
    seen: list[list[str]] = []
    modes: list[int] = []


@contextmanager
def served(folder: Path, body: bytes, status: int = 200) -> Iterator[int]:
    """The port of a route on this machine answering with this body and status."""
    Server.body = body
    Server.status = status
    Server.folder = folder
    Server.seen = []
    Server.modes = []
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def garbage() -> Iterator[int]:
    """The port of a listener that reads the request and answers what no HTTP client can parse."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def answering() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.recv(65536)
            connection.sendall(b"ECOSEMANTIC NOT HTTP\r\n\r\n")

    thread = threading.Thread(target=answering, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        listener.close()
        thread.join(timeout=5)


def stopped_at(port: int) -> str:
    """The stop route on this port of this machine."""
    return f"http://127.0.0.1:{port}/stop"


def test_a_listener_that_does_not_speak_http_is_no_answer(tmp_path: Path) -> None:
    with garbage() as port:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, stopped_at(port)) is None
    assert list(tmp_path.iterdir()) == []


def test_an_answer_that_is_not_json_is_no_answer(tmp_path: Path) -> None:
    with served(tmp_path, b"<html>another program</html>") as port:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, stopped_at(port)) is None
    assert list(tmp_path.iterdir()) == []


def test_an_answer_that_is_not_an_object_is_no_answer(tmp_path: Path) -> None:
    with served(tmp_path, b'["stopped"]') as port:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, stopped_at(port)) is None
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
    with served(tmp_path, b'{"stopped": true}') as port:
        assert asked_with_nonce(tmp_path, STOP_NONCE_FILE, stopped_at(port)) == {"stopped": True}
    assert Server.seen == [[STOP_NONCE_FILE]]
    assert Server.modes == [0o600]
    assert len(staged) == 1
    written, mode = staged[0]
    assert written.parent == tmp_path
    assert written.name.startswith(f".{STOP_NONCE_FILE}.")
    assert mode == 0o600
    assert list(tmp_path.iterdir()) == []


def test_a_nonce_of_any_value_is_refused_not_failed(tmp_path: Path) -> None:
    (tmp_path / STOP_NONCE_FILE).write_text("the-real-nonce", encoding="utf-8")
    (tmp_path / YIELD_NONCE_FILE).write_text("the-real-nonce", encoding="utf-8")
    for sent in ("é", 5):
        assert proven(sent, tmp_path, STOP_NONCE_FILE) is False
    ended: list[bool] = []
    app = Starlette(
        routes=[
            stop_route(tmp_path, lambda: ended.append(True)),
            yield_route(tmp_path, lambda: ended.append(True)),
        ]
    )
    with TestClient(app) as client:
        for path in ("/stop", "/yield"):
            for sent in ("é", 5):
                assert client.post(path, json={"nonce": sent}).status_code == 401
    assert ended == []


ENGINE = {
    "service": "ecosemantic-view",
    "workspace": "abcd1234abcd1234",
    "yields": True,
    "bridge": {
        "state": "connected",
        "handle": "ana",
        "page": "https://ana.bridge.example",
        "connector": "https://bridge.example/mcp",
    },
}


def test_read_health_answers_an_engines_health(tmp_path: Path) -> None:
    with served(tmp_path, json.dumps(ENGINE).encode()) as port:
        assert read_health(LOOPBACK_ADDRESS, port) == Health(
            service=SERVICE,
            workspace="abcd1234abcd1234",
            yields=True,
            bridge=BridgeHealth(
                state="connected",
                handle="ana",
                page="https://ana.bridge.example",
                connector="https://bridge.example/mcp",
            ),
        )


def test_read_health_is_none_where_nothing_answers() -> None:
    listener = socket.socket()
    listener.bind((LOOPBACK_ADDRESS, 0))
    port = listener.getsockname()[1]
    listener.close()
    assert read_health(LOOPBACK_ADDRESS, port) is None


@pytest.mark.parametrize(
    "answer",
    [
        b'{"service": "other"}',
        b"not json",
        b'{"service": "ecosemantic-view"}',
        # a health naming a tunnel state the relay does not have
        json.dumps({**ENGINE, "bridge": {"state": "asleep"}}).encode(),
    ],
)
def test_a_foreign_answer_is_not_a_health(tmp_path: Path, answer: bytes) -> None:
    with served(tmp_path, answer) as port:
        with pytest.raises(Unavailable, match=f"port {port} is held by another application"):
            read_health(LOOPBACK_ADDRESS, port)


def test_a_listener_that_does_not_speak_http_is_no_health() -> None:
    with garbage() as port:
        with pytest.raises(Unavailable, match=f"port {port} is held by another application"):
            read_health(LOOPBACK_ADDRESS, port)


@pytest.mark.parametrize("status", [404, 500])
def test_an_http_error_is_not_a_health(tmp_path: Path, status: int) -> None:
    with served(tmp_path, b"not here", status=status) as port:
        with pytest.raises(Unavailable, match=f"port {port} is held by another application") as e:
            read_health(LOOPBACK_ADDRESS, port)
    assert str(status) in str(e.value)


def test_a_refusal_carries_the_remedy_its_reader_names(tmp_path: Path) -> None:
    with served(tmp_path, b'{"service": "other"}') as port:
        with pytest.raises(Unavailable) as named:
            read_health(LOOPBACK_ADDRESS, port, hint="pass --view-port")
        with pytest.raises(Unavailable) as bare:
            read_health(LOOPBACK_ADDRESS, port)
    assert named.value.hint == "pass --view-port"
    assert bare.value.hint is None
