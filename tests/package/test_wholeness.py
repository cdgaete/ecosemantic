from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.package.wholeness import misses, require_whole, resolve_provider
from tests.openlca_fixture import FLOW_IDS, build_package


def test_the_provider_rule_is_the_readers() -> None:
    assert resolve_provider("a", ["a", "b"]) == ("a", "")
    assert resolve_provider("x", ["a"]) == (None, "its provider is not in the package")
    assert resolve_provider(None, ["a"]) == ("a", "")
    assert resolve_provider(None, ["a", "b"]) == (None, "several processes produce it")
    assert resolve_provider(None, []) == (None, "no process produces it")


def test_the_fixture_lacks_only_the_provider_it_names_outside_itself(tmp_path: Path) -> None:
    found = misses(build_package(tmp_path / "p.zip"))
    # the widget's fuel input names no provider and has one producer: it resolves
    assert [(m.process, m.exchange, m.lacks) for m in found] == [
        ("widget production", 4, "a provider: its provider is not in the package")
    ]


@pytest.mark.parametrize(
    ("knob", "lacks"),
    [("odd_unit", "unit furlong"), ("other_property", "its flow's reference property")],
)
def test_a_unit_or_property_that_does_not_resolve_is_a_miss(
    tmp_path: Path, knob: str, lacks: str
) -> None:
    found = misses(build_package(tmp_path / "p.zip", **{knob: True}))
    assert any(m.process == "steel production" and lacks in m.lacks for m in found)


def test_a_flow_without_flow_properties_is_refused_naming_its_exchanges(tmp_path: Path) -> None:
    source = build_package(tmp_path / "p.zip")
    stripped = tmp_path / "stripped.zip"
    member = f"flows/{FLOW_IDS['co2']}.json"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(stripped, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == member:
                flow = json.loads(data)
                flow.pop("flowProperties")
                data = json.dumps(flow).encode()
            dst.writestr(name, data)
    with pytest.raises(Invalid, match="Carbon dioxide, fossil") as raised:
        require_whole(stripped)
    assert "one reference flow property" in str(raised.value)
    assert "elec production" in str(raised.value)


def test_a_cut_off_is_whole_when_providers_are_not_asked(tmp_path: Path) -> None:
    assert misses(build_package(tmp_path / "p.zip"), providers=False) == []


def test_an_exchange_in_a_unit_its_group_lacks_is_named_without_providers(
    tmp_path: Path,
) -> None:
    found = misses(build_package(tmp_path / "p.zip", odd_unit=True), providers=False)
    assert [(m.process, m.lacks) for m in found] == [
        ("steel production", "unit furlong in its flow's unit group")
    ]
