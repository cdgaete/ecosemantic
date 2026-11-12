"""The unlinked and left-out lists a profile carries, read and written as CSV in key order."""

from __future__ import annotations

from pathlib import Path

import olca_schema as o
import pytest
from olca_schema.zipio import ZipWriter

from ecosemantic.databases import lists
from ecosemantic.databases.lists import (
    LeftOutRow,
    UnlinkedRow,
    read_left_out,
    read_unlinked,
    top_categories,
    top_category,
    write_left_out,
    write_unlinked,
)
from ecosemantic.errors import Invalid

UNLINKED = (
    UnlinkedRow(
        process_id="p1",
        process_name="Corn, at field",
        flow_id="f1",
        flow_name="Corn",
        flow_category="Technosphere Flows/Agricultural",
        provider_id="pr1",
    ),
    UnlinkedRow(
        process_id="p2",
        process_name="Diesel, at refinery",
        flow_id="f2",
        flow_name="Diesel",
        flow_category="Technosphere Flows/Energy carriers",
        provider_id=None,
    ),
)

LEFT_OUT = (
    LeftOutRow(
        process_id="p1",
        process_name="Corn, at field",
        exchange_id=4,
        flow_id="f4",
        flow_name="Natural gas",
        what="distribution",
        reason="refused",
    ),
    LeftOutRow(
        process_id="p2",
        process_name="Diesel, at refinery",
        exchange_id=3,
        flow_id="f3",
        flow_name="Crude oil",
        what="exchange",
        reason="refused",
    ),
)


def test_the_unlinked_list_round_trips_in_key_order(tmp_path: Path) -> None:
    path = tmp_path / "unlinked.csv"
    write_unlinked(path, reversed(UNLINKED))
    assert read_unlinked(path) == UNLINKED


def test_the_left_out_list_round_trips_in_key_order(tmp_path: Path) -> None:
    path = tmp_path / "left-out.csv"
    write_left_out(path, reversed(LEFT_OUT))
    assert read_left_out(path) == LEFT_OUT


def test_a_left_out_row_of_an_unknown_kind_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "left-out.csv"
    path.write_text(
        "process_id,process_name,exchange_id,flow_id,flow_name,what,reason\n"
        "p1,Corn at field,4,f4,Natural gas,other,refused\n",
        encoding="utf-8",
    )
    with pytest.raises(Invalid) as refused:
        read_left_out(path)
    message = str(refused.value)
    assert "left-out.csv" in message
    assert "p1" in message
    assert "f4" in message
    assert "other" in message


def _package(path: Path, category: str | None) -> Path:
    """A package holding one flow under `category`, written at `path`."""
    with ZipWriter(str(path)) as writer:
        writer.write(o.Flow(id="a-flow", name="a flow", category=category))
    return path


def test_a_flow_s_top_category_is_the_first_segment_of_its_path(tmp_path: Path) -> None:
    flow = o.Flow(id="f1", name="a flow", category="Technosphere flows/31-33: Manufacturing")
    assert top_category(flow) == "Technosphere flows"
    assert top_category(o.Flow(id="f2", name="an uncategorised flow")) == ""

    first = _package(tmp_path / "first.zip", "Technosphere flows/31-33: Manufacturing")
    second = _package(tmp_path / "second.zip", "Ecosystem Services/Provisioning")

    assert top_categories(first, second) == {"a-flow": "Technosphere flows"}


def test_no_source_spells_a_flow_s_top_category() -> None:
    root = Path(lists.__file__).parent
    spelled = [
        path
        for path in root.rglob("*.py")
        if path.name != "lists.py" and '.split("/")[0]' in path.read_text(encoding="utf-8")
    ]
    assert spelled == []
    assert not hasattr(lists, "flow_categories")


def test_the_lists_carry_the_specification_s_columns(tmp_path: Path) -> None:
    unlinked = tmp_path / "unlinked.csv"
    left_out = tmp_path / "left-out.csv"
    write_unlinked(unlinked, UNLINKED)
    write_left_out(left_out, LEFT_OUT)
    assert unlinked.read_text(encoding="utf-8").splitlines()[0] == (
        "process_id,process_name,flow_id,flow_name,flow_category,provider_id"
    )
    assert left_out.read_text(encoding="utf-8").splitlines()[0] == (
        "process_id,process_name,exchange_id,flow_id,flow_name,what,reason"
    )
