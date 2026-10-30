from __future__ import annotations

import http.server
import io
import json
import logging
import os
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import pytest
import truststore
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
    MetricExportResult,
)

from ecosemantic import telemetry
from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.telemetry import Choice, begin, chosen, end, record, serving, status


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv(telemetry.SWITCH, raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv(telemetry.ENDPOINT_VARIABLE, raising=False)


def kept(data_dir: Path) -> dict:
    return json.loads((data_dir / telemetry.FILE).read_text(encoding="utf-8"))


def test_on_by_default(tmp_path):
    assert chosen({}, tmp_path) == Choice(True, "default")


def test_the_switch_wins_over_do_not_track_and_the_file(tmp_path):
    record({}, tmp_path, False)
    environ = {"ECOSEMANTIC_TELEMETRY": "ON", "DO_NOT_TRACK": "1"}
    assert chosen(environ, tmp_path) == Choice(True, "ECOSEMANTIC_TELEMETRY")


def test_a_mistyped_switch_is_refused(tmp_path):
    with pytest.raises(Invalid, match="ECOSEMANTIC_TELEMETRY"):
        chosen({"ECOSEMANTIC_TELEMETRY": "no"}, tmp_path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", Choice(False, "DO_NOT_TRACK")),
        ("true", Choice(False, "DO_NOT_TRACK")),
        ("yes", Choice(False, "DO_NOT_TRACK")),
        ("", Choice(True, "default")),
        ("0", Choice(True, "default")),
    ],
)
def test_do_not_track(tmp_path, value, expected):
    assert chosen({"DO_NOT_TRACK": value}, tmp_path) == expected


def test_the_recorded_choice(tmp_path):
    record({}, tmp_path / "made", False)
    assert chosen({}, tmp_path / "made") == Choice(False, "telemetry.json")
    assert "install_id" not in kept(tmp_path / "made")


KEPT_ID = "6f1c0b52-2d57-4c1e-9a54-0c3f6f0d8a11"


def test_record_keeps_the_other_keys(tmp_path):
    (tmp_path / telemetry.FILE).write_text(
        json.dumps({"install_id": KEPT_ID, "told": True}), encoding="utf-8"
    )
    record({}, tmp_path, True)
    assert kept(tmp_path) == {"choice": "on", "install_id": KEPT_ID, "told": True}


def test_record_refuses_a_mistyped_switch_before_writing(tmp_path):
    with pytest.raises(Invalid, match="ECOSEMANTIC_TELEMETRY"):
        record({"ECOSEMANTIC_TELEMETRY": "no"}, tmp_path, False)
    assert not (tmp_path / telemetry.FILE).exists()


@pytest.mark.parametrize(
    "text",
    [
        "{",
        '{"choice": "maybe"}',
        "[]",
        '{"install_id": "ABC"}',
        '{"install_id": 7}',
        '{"install_id": "6F1C0B52-2D57-4C1E-9A54-0C3F6F0D8A11"}',
        '{"install_id": "6f1c0b52-2d57-1c1e-9a54-0c3f6f0d8a11"}',
    ],
)
def test_a_broken_file_is_refused_with_its_remedy(tmp_path, text):
    (tmp_path / telemetry.FILE).write_text(text, encoding="utf-8")
    with pytest.raises(Invalid, match="telemetry.json") as refused:
        chosen({}, tmp_path)
    assert "delete it" in str(refused.value)
    assert "ecosemantic telemetry on" in str(refused.value)


def test_a_file_that_is_not_utf8_is_refused_with_its_remedy(tmp_path):
    (tmp_path / telemetry.FILE).write_text('{"choice": "off"}', encoding="utf-16")
    with pytest.raises(Invalid, match="telemetry.json") as refused:
        chosen({}, tmp_path)
    assert "UTF-8" in str(refused.value)
    assert "delete it" in str(refused.value)


def test_a_file_that_cannot_be_read_is_unavailable(tmp_path):
    (tmp_path / telemetry.FILE).mkdir()
    with pytest.raises(Unavailable, match="telemetry.json") as refused:
        status({}, tmp_path)
    assert refused.value.hint is not None


def test_a_recorded_choice_and_identifier_are_read_back(tmp_path):
    (tmp_path / telemetry.FILE).write_text(
        json.dumps({"choice": "on", "install_id": KEPT_ID, "told": True}), encoding="utf-8"
    )
    assert status({}, tmp_path)["install_id"] == KEPT_ID


@pytest.mark.parametrize(
    "environ",
    [{}, {"ECOSEMANTIC_TELEMETRY": "on"}, {"ECOSEMANTIC_TELEMETRY": "off"}, {"DO_NOT_TRACK": "1"}],
)
def test_chosen_and_begin_agree_on_a_broken_file(tmp_path, environ):
    (tmp_path / telemetry.FILE).write_text("{broken", encoding="utf-8")
    outcomes = []
    reader = InMemoryMetricReader()
    for decide in (
        lambda: chosen(environ, tmp_path).on,
        lambda: begin(environ, tmp_path, "stdio", io.StringIO(), reader) is not None,
    ):
        try:
            outcomes.append(decide())
        except Invalid:
            outcomes.append("refused")
    assert outcomes[0] == outcomes[1]


def test_off_makes_nothing(tmp_path):
    stream = io.StringIO()
    provider = begin({"ECOSEMANTIC_TELEMETRY": "off"}, tmp_path, "stdio", stream)
    assert provider is None
    assert not (tmp_path / telemetry.FILE).exists()
    assert stream.getvalue() == ""
    end(provider)


def test_the_first_start_tells_once(tmp_path):
    stream = io.StringIO()
    for _ in range(2):
        begin({}, tmp_path, "stdio", stream, InMemoryMetricReader())
    assert stream.getvalue() == telemetry.NOTICE + "\n"
    assert kept(tmp_path)["told"] is True


def test_a_recorded_choice_is_not_told(tmp_path):
    record({}, tmp_path, True)
    stream = io.StringIO()
    begin({}, tmp_path, "stdio", stream, InMemoryMetricReader())
    assert stream.getvalue() == ""


def test_the_identifier_is_a_kept_uuid4(tmp_path):
    for _ in range(2):
        begin({}, tmp_path, "stdio", io.StringIO(), InMemoryMetricReader())
        first = status({}, tmp_path)["install_id"]
    assert isinstance(first, str)
    assert uuid.UUID(first).version == 4
    assert kept(tmp_path)["install_id"] == first


def test_status_without_an_identifier(tmp_path):
    assert status({}, tmp_path) == {
        "on": True,
        "reason": "default",
        "install_id": None,
        "endpoint": telemetry.ENDPOINT,
        "file": str(tmp_path / telemetry.FILE),
    }


def test_status_names_the_endpoint_override(tmp_path):
    named = {telemetry.ENDPOINT_VARIABLE: "http://127.0.0.1:1/v1/metrics"}
    assert status(named, tmp_path)["endpoint"] == "http://127.0.0.1:1/v1/metrics"


def test_a_start_is_counted_under_the_allowed_resource(tmp_path):
    reader = InMemoryMetricReader()
    begin({}, tmp_path, "stdio", io.StringIO(), reader)
    data = reader.get_metrics_data()
    assert data is not None
    resource = data.resource_metrics[0]
    assert dict(resource.resource.attributes) == {
        "service.name": "ecosemantic",
        "service.version": version("ecosemantic"),
        "service.instance.id": kept(tmp_path)["install_id"],
        "os.type": sys.platform,
        "ecosemantic.transport": "stdio",
    }
    metrics = resource.scope_metrics[0].metrics
    assert [metric.name for metric in metrics] == [telemetry.STARTS]
    points = metrics[0].data.data_points
    assert len(points) == 1
    assert points[0].value == 1
    assert not points[0].attributes


class Collector(http.server.BaseHTTPRequestHandler):
    bodies: list[tuple[str, bytes]]
    status = 200

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.server.bodies.append((self.path, self.rfile.read(length)))
        self.send_response(self.server.answer)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(answer: int):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    server.bodies = []
    server.answer = answer
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop(server) -> None:
    server.shutdown()
    server.server_close()


def self_signed(directory: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "collector.pem"
    key_path = directory / "collector.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


def serve_tls(certificate: Path, key: Path):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    server.bodies = []
    server.answer = 200
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_shutdown_sends_delta_counts_to_the_endpoint(tmp_path):
    server = serve(200)
    port = server.server_address[1]
    environ = {telemetry.ENDPOINT_VARIABLE: f"http://127.0.0.1:{port}/v1/metrics"}
    provider = begin(environ, tmp_path, "http", io.StringIO())
    end(provider)
    stop(server)
    assert len(server.bodies) == 1
    path, body = server.bodies[0]
    assert path == "/v1/metrics"
    request = ExportMetricsServiceRequest()
    request.ParseFromString(body)
    metric = request.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == telemetry.STARTS
    assert metric.sum.aggregation_temporality == AggregationTemporality.DELTA


def test_the_exporter_verifies_with_the_operating_system_s_trust_store(tmp_path, monkeypatch):
    reader = InMemoryMetricReader()
    begin({}, tmp_path, "stdio", io.StringIO(), reader)
    data = reader.get_metrics_data()
    assert data is not None
    contexts = []

    def held(request: urllib.request.Request, **kwargs: object) -> object:
        contexts.append(kwargs["context"])
        raise OSError("held")

    monkeypatch.setattr(urllib.request, "urlopen", held)
    exporter = telemetry.Exporter("https://collector.invalid/v1/metrics")
    results = [exporter.export(data) for _ in range(2)]
    assert results == [MetricExportResult.FAILURE, MetricExportResult.FAILURE]
    assert len(contexts) == 2
    assert all(isinstance(context, truststore.SSLContext) for context in contexts)
    assert contexts[0] is contexts[1]


def test_a_refused_certificate_is_an_info_line(tmp_path, caplog):
    certificate, key = self_signed(tmp_path)
    server = serve_tls(certificate, key)
    endpoint = f"https://127.0.0.1:{server.server_address[1]}/v1/metrics"
    caplog.set_level(logging.INFO, logger=telemetry.LOG.name)
    try:
        end(begin({telemetry.ENDPOINT_VARIABLE: endpoint}, tmp_path, "stdio", io.StringIO()))
    finally:
        stop(server)
    assert server.bodies == []
    recorded = [entry for entry in caplog.records if entry.name == telemetry.LOG.name]
    assert [entry.levelno for entry in recorded] == [logging.INFO]
    assert recorded[0].getMessage().startswith(f"telemetry not sent to {endpoint}: ")
    assert [entry for entry in caplog.records if entry.levelno >= logging.WARNING] == []


@pytest.fixture
def no_lookup(monkeypatch):
    real = socket.getaddrinfo

    def refuse(host, *args, **kwargs):
        if host == "telemetry.invalid":
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def silent_socket():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    held = []
    stop = threading.Event()

    def accept():
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(listener.accept()[0])
            except OSError:
                continue

    threading.Thread(target=accept, daemon=True).start()
    yield listener.getsockname()[1]
    stop.set()
    for connection in held:
        connection.close()
    listener.close()


def out_of_service(kind: str, request: pytest.FixtureRequest):
    if kind == "closed":
        return "http://127.0.0.1:9/v1/metrics"
    if kind == "unresolved":
        return "http://telemetry.invalid/v1/metrics"
    if kind == "unavailable":
        server = serve(503)
        request.addfinalizer(lambda: stop(server))
        return f"http://127.0.0.1:{server.server_address[1]}/v1/metrics"
    return f"http://127.0.0.1:{request.getfixturevalue('silent_socket')}/v1/metrics"


@pytest.mark.usefixtures("no_lookup")
@pytest.mark.parametrize("kind", ["closed", "unresolved", "unavailable", "silent"])
def test_an_unreachable_collector_holds_the_stop_at_most_the_timeout(tmp_path, kind, request):
    environ = {telemetry.ENDPOINT_VARIABLE: out_of_service(kind, request)}
    began = time.monotonic()
    provider = begin(environ, tmp_path, "stdio", io.StringIO())
    assert time.monotonic() - began < 1
    assert provider is not None
    provider.get_meter("ecosemantic").create_counter("calls").add(1, {"tool": "x"})
    stopping = time.monotonic()
    end(provider)
    assert time.monotonic() - stopping < 7


def test_the_environment_adds_nothing_to_what_is_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "authorization=secret")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_HEADERS", "x-api-key=k")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "60")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    server = serve(200)
    seen = []
    handler = server.RequestHandlerClass
    original = handler.do_POST

    def post(self):
        seen.append({name.lower() for name in self.headers})
        original(self)

    monkeypatch.setattr(handler, "do_POST", post)
    environ = {
        telemetry.ENDPOINT_VARIABLE: f"http://127.0.0.1:{server.server_address[1]}/v1/metrics"
    }
    end(begin(environ, tmp_path, "stdio", io.StringIO()))
    stop(server)
    assert len(seen) == 1
    assert not seen[0] & {"authorization", "x-api-key"}
    path, body = server.bodies[0]
    assert path == "/v1/metrics"
    request = ExportMetricsServiceRequest()
    request.ParseFromString(body)
    metric = request.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.sum.aggregation_temporality == AggregationTemporality.DELTA


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="root writes anywhere; chmod does not make a Windows directory read-only",
)
def test_an_unwritable_data_directory_refuses_the_start(tmp_path):
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(Unavailable, match="telemetry.json"):
            begin({}, tmp_path, "stdio", io.StringIO(), InMemoryMetricReader())
    finally:
        tmp_path.chmod(0o700)


def test_an_endpoint_that_is_not_http_is_refused(tmp_path):
    environ = {telemetry.ENDPOINT_VARIABLE: "file:///etc/passwd"}
    with pytest.raises(Invalid, match=telemetry.ENDPOINT_VARIABLE):
        begin(environ, tmp_path, "stdio", io.StringIO())


def test_end_without_a_provider():
    end(None)


def test_a_given_reader_builds_the_provider(tmp_path):
    provider = begin({}, tmp_path, "stdio", io.StringIO(), InMemoryMetricReader())
    assert isinstance(provider, MeterProvider)


@pytest.mark.parametrize(
    ("environ", "reason"),
    [
        ({"ECOSEMANTIC_TELEMETRY": "off"}, "ECOSEMANTIC_TELEMETRY"),
        ({"DO_NOT_TRACK": "1"}, "DO_NOT_TRACK"),
    ],
)
def test_the_off_switch_wins_over_a_broken_file(tmp_path, environ, reason):
    (tmp_path / telemetry.FILE).write_text("{broken", encoding="utf-8")
    assert chosen(environ, tmp_path) == Choice(False, reason)
    assert begin(environ, tmp_path, "stdio", io.StringIO()) is None


def test_serving_ends_the_provider_when_the_block_ends(tmp_path):
    server = serve(200)
    environ = {
        telemetry.ENDPOINT_VARIABLE: f"http://127.0.0.1:{server.server_address[1]}/v1/metrics"
    }
    before = signal.getsignal(signal.SIGTERM)
    with serving(begin(environ, tmp_path, "stdio", io.StringIO())):
        assert signal.getsignal(signal.SIGTERM) is not before
    stop(server)
    assert signal.getsignal(signal.SIGTERM) is before
    assert len(server.bodies) == 1


def test_serving_without_a_provider_leaves_the_signal_alone():
    before = signal.getsignal(signal.SIGTERM)
    with serving(None):
        assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.skipif(sys.platform == "win32", reason="Windows delivers no SIGTERM to a process")
def test_sigterm_inside_serving_sends_the_report_then_re_raises(tmp_path, monkeypatch):
    server = serve(200)
    environ = {
        telemetry.ENDPOINT_VARIABLE: f"http://127.0.0.1:{server.server_address[1]}/v1/metrics"
    }
    raised = []
    monkeypatch.setattr(signal, "raise_signal", raised.append)
    with serving(begin(environ, tmp_path, "stdio", io.StringIO())):
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
        assert len(server.bodies) == 1
    stop(server)
    assert raised == [signal.SIGTERM]
    assert len(server.bodies) == 1


def test_a_failing_end_still_re_raises_the_signal(tmp_path, monkeypatch):
    raised = []
    monkeypatch.setattr(signal, "raise_signal", raised.append)

    def failing(provider):
        raise RuntimeError("boom")

    provider = begin({}, tmp_path, "stdio", io.StringIO(), InMemoryMetricReader())
    with serving(provider):
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        monkeypatch.setattr(telemetry, "end", failing)
        with pytest.raises(RuntimeError):
            handler(signal.SIGTERM, None)
        monkeypatch.undo()
    assert raised == [signal.SIGTERM]


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "1"},
    },
}


@pytest.mark.skipif(sys.platform == "win32", reason="Windows delivers no SIGTERM to a process")
@pytest.mark.parametrize("view", [False, True], ids=["stdio alone", "stdio beside the page"])
def test_a_server_stopped_by_sigterm_sends_its_report(tmp_path, view):
    server = serve(200)
    (tmp_path / "data").mkdir()
    (tmp_path / "systems").mkdir()
    command = [
        str(Path(sys.executable).parent / "ecosemantic"),
        "serve",
        "--data-dir",
        str(tmp_path / "data"),
        "--systems-dir",
        str(tmp_path / "systems"),
        "--no-open",
        *(["--view-port", "0"] if view else ["--no-view"]),
    ]
    environ = {
        **os.environ,
        telemetry.SWITCH: "on",
        telemetry.ENDPOINT_VARIABLE: f"http://127.0.0.1:{server.server_address[1]}/v1/metrics",
    }
    served = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environ,
    )
    try:
        assert served.stdin is not None and served.stdout is not None
        served.stdin.write((json.dumps(INITIALIZE) + "\n").encode())
        served.stdin.flush()
        assert json.loads(served.stdout.readline())["id"] == 1
        served.send_signal(signal.SIGTERM)
        code = served.wait(15)
    finally:
        served.kill()
        stop(server)
    assert code == -signal.SIGTERM
    assert len(server.bodies) == 1


def test_no_exemplar_is_attached(tmp_path, monkeypatch):
    from opentelemetry import trace

    monkeypatch.setenv("OTEL_METRICS_EXEMPLAR_FILTER", "always_on")
    reader = InMemoryMetricReader()
    provider = begin({}, tmp_path, "stdio", io.StringIO(), reader)
    span = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=0x1234,
            span_id=0x5678,
            is_remote=True,
            trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
        )
    )
    with trace.use_span(span):
        calls = provider.get_meter("ecosemantic").create_counter("ecosemantic.tool.calls")
        calls.add(1, {"tool": "x"})
    points = [
        point
        for resource in reader.get_metrics_data().resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        for point in metric.data.data_points
    ]
    assert len(points) == 2
    assert all(not point.exemplars for point in points)
