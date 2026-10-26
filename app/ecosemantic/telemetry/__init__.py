"""Anonymous counts of server starts and tool calls: whether they are on, the install identifier
kept beside the data, and the meter provider that sends them."""

from __future__ import annotations

import contextlib
import http.client
import json
import logging
import os
import signal
import sys
import tempfile
import urllib.request
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from types import FrameType
from typing import Literal, TextIO

from opentelemetry.exporter.otlp.proto.common.metrics_encoder import encode_metrics
from opentelemetry.sdk.metrics import AlwaysOffExemplarFilter, Counter, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    MetricReader,
    MetricsData,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.mcp.counting import METER
from ecosemantic.serve import Transport

SWITCH = "ECOSEMANTIC_TELEMETRY"
DO_NOT_TRACK = "DO_NOT_TRACK"
ENDPOINT_VARIABLE = "ECOSEMANTIC_TELEMETRY_ENDPOINT"
ENDPOINT = "https://telemetry.ecosemantic.com/v1/metrics"
FILE = "telemetry.json"
STARTS = "ecosemantic.server.starts"
INTERVAL_MILLIS = 3_600_000
TIMEOUT_MILLIS = 5_000
NOTICE = (
    "EcoSemantic sends counts of server starts and tool calls, under a random install "
    "identifier, so its author can see how many people use it. `ecosemantic telemetry off` "
    "turns it off for every server on this machine. What is sent: "
    "https://github.com/cdgaete/ecosemantic/blob/main/TELEMETRY.md"
)
CHOICES = ("on", "off")
CONTENT_TYPE = "application/x-protobuf"
LOG = logging.getLogger("opentelemetry.ecosemantic")

Reason = Literal["ECOSEMANTIC_TELEMETRY", "DO_NOT_TRACK", "telemetry.json", "default"]


@dataclass(frozen=True)
class Choice:
    """Whether telemetry is on and which setting decided it."""

    on: bool
    reason: Reason


def _refused(path: Path, why: str) -> Invalid:
    return Invalid(
        f"{path} {why}; delete it, then run `ecosemantic telemetry on` or "
        "`ecosemantic telemetry off` to record the choice"
    )


def _identifier(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.variant == uuid.RFC_4122 and str(parsed) == value


def _read(data_dir: Path) -> dict[str, object]:
    path = data_dir / FILE
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _refused(path, "is not UTF-8 text") from error
    except OSError as error:
        raise Unavailable(
            f"cannot read {path}: {error.strerror}",
            hint=f"make {path} a file this user can read, or remove it",
        ) from error
    try:
        held = json.loads(text)
    except json.JSONDecodeError as error:
        raise _refused(path, f"is not JSON ({error.msg})") from error
    if not isinstance(held, dict):
        raise _refused(path, "does not hold an object")
    if "choice" in held and held["choice"] not in CHOICES:
        raise _refused(path, f"holds the choice {held['choice']!r}, not on or off")
    if "install_id" in held and not _identifier(held["install_id"]):
        raise _refused(path, f"holds the install identifier {held['install_id']!r}, not a UUID4")
    return held


def _write(data_dir: Path, held: dict[str, object]) -> None:
    path = data_dir / FILE
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=data_dir, prefix=f"{FILE}.")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(held, handle)
        os.replace(temporary, path)
    except OSError as error:
        raise Unavailable(
            f"cannot write {path}: {error.strerror}",
            hint="make the data directory writable or set ECOSEMANTIC_TELEMETRY=off",
        ) from error


def _switched(environ: Mapping[str, str]) -> Choice | None:
    named = environ.get(SWITCH)
    if named is not None:
        if named.lower() not in CHOICES:
            raise Invalid(f"{SWITCH} {named!r} is neither on nor off")
        return Choice(named.lower() == "on", "ECOSEMANTIC_TELEMETRY")
    if environ.get(DO_NOT_TRACK, "") not in ("", "0"):
        return Choice(False, "DO_NOT_TRACK")
    return None


def _decided(
    environ: Mapping[str, str], data_dir: Path, *, always_read: bool = False
) -> tuple[Choice, dict[str, object]]:
    """The choice and what telemetry.json holds. A switch that turns telemetry off decides
    without the file, unless `always_read`, so a damaged file cannot refuse a start the person
    turned off; a switch that turns it on still reads the file for the kept identifier."""
    switched = _switched(environ)
    if switched is not None and not switched.on and not always_read:
        return switched, {}
    held = _read(data_dir)
    if switched is not None:
        return switched, held
    recorded = held.get("choice")
    if recorded is None:
        return Choice(True, "default"), held
    return Choice(recorded == "on", "telemetry.json"), held


def chosen(environ: Mapping[str, str], data_dir: Path) -> Choice:
    """Whether telemetry is on: the switch, then DO_NOT_TRACK, then the recorded choice."""
    return _decided(environ, data_dir)[0]


def record(environ: Mapping[str, str], data_dir: Path, on: bool) -> None:
    """Writes the choice to telemetry.json, keeping its other keys. A mistyped
    ECOSEMANTIC_TELEMETRY refuses it before anything is written."""
    _switched(environ)
    held = _read(data_dir)
    held["choice"] = "on" if on else "off"
    _write(data_dir, held)


def status(environ: Mapping[str, str], data_dir: Path) -> dict[str, object]:
    """The choice, its reason, the kept identifier if any, the endpoint and the file."""
    decided, held = _decided(environ, data_dir, always_read=True)
    return {
        "on": decided.on,
        "reason": decided.reason,
        "install_id": held.get("install_id"),
        "endpoint": environ.get(ENDPOINT_VARIABLE, ENDPOINT),
        "file": str(data_dir / FILE),
    }


class Exporter(MetricExporter):
    """Posts OTLP protobuf to one endpoint with the content type and nothing taken from the
    environment; a post that fails drops the batch."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(preferred_temporality={Counter: AggregationTemporality.DELTA})
        if not endpoint.startswith(("http://", "https://")):
            raise Invalid(f"{ENDPOINT_VARIABLE} {endpoint!r} is not an http or https address")
        self.endpoint = endpoint

    def export(
        self, metrics_data: MetricsData, timeout_millis: float = TIMEOUT_MILLIS, **kwargs: object
    ) -> MetricExportResult:
        request = urllib.request.Request(
            self.endpoint,
            data=encode_metrics(metrics_data).SerializeToString(),
            headers={"Content-Type": CONTENT_TYPE},
            method="POST",
        )
        seconds = min(timeout_millis, TIMEOUT_MILLIS) / 1000
        try:
            with urllib.request.urlopen(request, timeout=seconds):
                return MetricExportResult.SUCCESS
        except (OSError, http.client.HTTPException) as error:
            LOG.warning("telemetry not sent to %s: %s", self.endpoint, error)
            return MetricExportResult.FAILURE

    def force_flush(self, timeout_millis: float = TIMEOUT_MILLIS) -> bool:
        del timeout_millis
        return True

    def shutdown(self, timeout_millis: float = TIMEOUT_MILLIS, **kwargs: object) -> None:
        del timeout_millis, kwargs


def _reader(endpoint: str) -> MetricReader:
    return PeriodicExportingMetricReader(
        Exporter(endpoint),
        export_interval_millis=INTERVAL_MILLIS,
        export_timeout_millis=TIMEOUT_MILLIS,
    )


def begin(
    environ: Mapping[str, str],
    data_dir: Path,
    transport: Transport,
    stream: TextIO,
    reader: MetricReader | None = None,
) -> MeterProvider | None:
    """Starts counting when telemetry is on: tells the person once, keeps the identifier and
    counts this start. Nothing is sent until the reader exports."""
    decided, held = _decided(environ, data_dir)
    if not decided.on:
        return None
    tell = "choice" not in held and not held.get("told")
    install_id = str(held.get("install_id") or uuid.uuid4())
    if tell or "install_id" not in held:
        held["install_id"] = install_id
        if tell:
            held["told"] = True
        _write(data_dir, held)
    if tell:
        stream.write(NOTICE + "\n")
    resource = Resource(
        {
            "service.name": "ecosemantic",
            "service.version": version("ecosemantic"),
            "service.instance.id": install_id,
            "os.type": sys.platform,
            "ecosemantic.transport": transport,
        }
    )
    provider = MeterProvider(
        metric_readers=[reader or _reader(environ.get(ENDPOINT_VARIABLE, ENDPOINT))],
        resource=resource,
        exemplar_filter=AlwaysOffExemplarFilter(),
    )
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    provider.get_meter(METER).create_counter(STARTS, description="Server starts").add(1)
    return provider


def end(provider: MeterProvider | None) -> None:
    """Sends what was counted and stops the provider, within the shutdown timeout."""
    if provider is not None:
        provider.shutdown(timeout_millis=TIMEOUT_MILLIS)


@contextlib.contextmanager
def serving(provider: MeterProvider | None) -> Iterator[None]:
    """Sends the final report when the server stops: when the block returns or raises, and on
    SIGTERM, after which the signal ends the process with its default action. Each waits at most
    the shutdown timeout."""
    if provider is None:
        yield
        return

    def terminated(signum: int, frame: FrameType | None) -> None:
        del frame
        try:
            end(provider)
        finally:
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    previous = signal.signal(signal.SIGTERM, terminated)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
        end(provider)
