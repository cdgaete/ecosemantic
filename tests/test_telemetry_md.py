from __future__ import annotations

import io
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ecosemantic import telemetry
from ecosemantic.mcp.counting import TOOL_CALLS

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def started(tmp_path):
    return started_attributes(tmp_path)


def started_attributes(tmp_path: Path) -> list[str]:
    reader = InMemoryMetricReader()
    provider = telemetry.begin({}, tmp_path, "stdio", io.StringIO(), reader)
    assert provider is not None
    resource = reader.get_metrics_data().resource_metrics[0].resource
    provider.shutdown()
    return list(resource.attributes)


def test_the_page_names_what_the_code_sends(started):
    page = (ROOT / "TELEMETRY.md").read_text(encoding="utf-8")
    names = [
        telemetry.STARTS,
        TOOL_CALLS,
        telemetry.ENDPOINT,
        telemetry.SWITCH,
        telemetry.ENDPOINT_VARIABLE,
        telemetry.DO_NOT_TRACK,
        "ecosemantic telemetry off",
        *started,
        "24 months",
        "unauthenticated",
        "`other`",
        "5 second",
    ]
    assert [name for name in names if name not in page] == []
    assert len(started) == 5


def test_the_readme_links_the_page():
    assert "(TELEMETRY.md)" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_page_names_the_meter_and_the_descriptions_sent(tmp_path):
    from ecosemantic.mcp.counting import Counting

    reader = InMemoryMetricReader()
    provider = telemetry.begin({}, tmp_path, "stdio", io.StringIO(), reader)
    assert provider is not None
    Counting(["list_databases"], provider).calls.add(1, {"tool": "list_databases"})
    scope = reader.get_metrics_data().resource_metrics[0].scope_metrics
    provider.shutdown()
    assert [item.scope.name for item in scope] == ["ecosemantic"]
    sent = {metric.name: metric.description for metric in scope[0].metrics}
    assert set(sent) == {telemetry.STARTS, TOOL_CALLS}
    page = (ROOT / "TELEMETRY.md").read_text(encoding="utf-8")
    assert "meter named `ecosemantic`" in page
    assert [d for d in sent.values() if f"`{d}`" not in page] == []
