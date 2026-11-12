from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from ecosemantic import files
from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.log import LOG_FILE, next_entry, read_log, write_log
from ecosemantic.package.requests import (
    REQUESTS_FILE,
    next_request,
    read_requests,
    write_requests,
)
from ecosemantic.package.sidecar import (
    LAYOUT_FILE,
    SIDECAR_DIR,
    ActivityRecord,
    ExchangeIdentity,
    Identities,
    ProcessIdentity,
    ProjectRecord,
    Sidecar,
    parsed_lines,
    read_layout,
    read_sidecar,
    write_layout,
    write_lines,
    write_sidecar,
)
from ecosemantic.ports.types import Layout, RequestDraft, Spot
from tests.conftest import CO2, COTTON

WORKING_VERSION_HINT = "open this product system with the version of ecosemantic that wrote it"


def stored(tmp_path: Path, product_system: ProductSystem) -> None:
    """A sidecar holding the product system's own parts."""
    write_sidecar(
        tmp_path,
        Sidecar(
            product_system=ProjectRecord(
                id=product_system.id,
                name=product_system.name,
                description=product_system.description,
                notes=product_system.notes,
                database=product_system.database,
                hash="0" * 64,
                processes=[ActivityRecord(id=a.id, code=a.code) for a in product_system.processes],
            ),
            identities=Identities(parameter_prefix="cotton_tshirt__"),
            scenarios=[],
            metadata={},
        ),
    )


def test_sidecar_round_trips_through_files(product_system: ProductSystem, tmp_path: Path) -> None:
    first = product_system.processes[0]
    sidecar = Sidecar(
        product_system=ProjectRecord(
            id=product_system.id,
            name=product_system.name,
            description=product_system.description,
            notes=product_system.notes,
            database=product_system.database,
            hash="0" * 64,
            processes=[ActivityRecord(id=a.id, code=a.code) for a in product_system.processes],
        ),
        identities=Identities(
            processes={str(first.id): ProcessIdentity(id=first.id, code="tshirt")},
            exchanges={
                f"{first.id}:1": ExchangeIdentity(id=first.exchanges[0].id, label="cotton t-shirt")
            },
            elementary_flows={"f2": CO2},
            suppliers={"p1:f1": COTTON},
            product_flows={"pf": product_system.processes[1].id},
            locations={"loc": "CH"},
            parameter_prefix="cotton_tshirt__",
        ),
        scenarios=product_system.scenarios,
        metadata={a.id: a.metadata for a in product_system.processes},
    )
    write_sidecar(tmp_path, sidecar)
    assert sorted(p.name for p in (tmp_path / SIDECAR_DIR).iterdir()) == [
        "identities.json",
        "metadata.json",
        "product_system.json",
        "scenarios.json",
    ]
    assert read_sidecar(tmp_path) == sidecar


def test_read_sidecar_requires_the_folder(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        read_sidecar(tmp_path)


def test_identities_default_empty() -> None:
    assert Identities(parameter_prefix="x__").processes == {}


def test_parsed_lines_reads_each_line_as_its_model_and_a_missing_file_reads_as_none(
    tmp_path: Path,
) -> None:
    class QueueEntry(BaseModel):
        a: int

    path = tmp_path / SIDECAR_DIR / "queue.jsonl"
    assert parsed_lines(path, QueueEntry, "remove it") == []
    write_lines(tmp_path, "queue.jsonl", ['{"a": 1}', '{"a": 2}'])
    assert path.read_text(encoding="utf-8") == '{"a": 1}\n{"a": 2}\n'
    path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    assert parsed_lines(path, QueueEntry, "remove it") == [QueueEntry(a=1), QueueEntry(a=2)]


def test_every_stored_document_this_version_cannot_read_is_unavailable(
    product_system: ProductSystem, tmp_path: Path
) -> None:
    stored(tmp_path, product_system)
    folder = tmp_path / SIDECAR_DIR
    assert read_layout(tmp_path) == Layout()
    write_lines(tmp_path, REQUESTS_FILE, ['{"bad": 1}'])
    write_lines(tmp_path, LOG_FILE, ['{"bad": 1}'])
    (folder / LAYOUT_FILE).write_text('{"held": {"a": 1}}', encoding="utf-8")
    (folder / "metadata.json").write_text('{"bad": {}}', encoding="utf-8")
    refusals: list[tuple[Callable[[Path], object], str, str]] = [
        (
            read_requests,
            "requests.jsonl line 1",
            f"remove {folder / REQUESTS_FILE} to drop the product system's requests",
        ),
        (read_log, "log.jsonl line 1", WORKING_VERSION_HINT),
        (read_sidecar, "metadata.json", WORKING_VERSION_HINT),
        (
            read_layout,
            "layout.json",
            f"remove {folder / LAYOUT_FILE}; the drawing places its cards again",
        ),
    ]
    for reader, named, hint in refusals:
        with pytest.raises(Unavailable) as caught:
            reader(tmp_path)
        assert str(caught.value).startswith(f"{named} cannot be read by this version: ")
        assert caught.value.hint == hint


def test_a_failed_write_leaves_the_previous_file_whole(
    product_system: ProductSystem, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored(tmp_path, product_system)
    folder = tmp_path / SIDECAR_DIR
    draft = RequestDraft(
        actor=Actor(kind="person", name="Carlos"),
        kind="return",
        at_hash="a" * 64,
        message="check this",
    )
    write_layout(tmp_path, Layout())
    write_requests(tmp_path, [next_request([], draft)])
    write_log(
        tmp_path,
        [next_entry([], Actor(kind="agent", id="claude"), "mcp", None, product_system, "created")],
    )
    first = read_sidecar(tmp_path)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}

    def held(source: object, destination: object) -> None:
        raise PermissionError(13, "the file is held by another process")

    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0)
    monkeypatch.setattr(os, "replace", held)
    writes: list[Callable[[], None]] = [
        lambda: write_layout(tmp_path, Layout(held={"a": Spot(x=1, y=2)})),
        lambda: write_requests(tmp_path, []),
        lambda: write_log(tmp_path, []),
        lambda: write_sidecar(
            tmp_path,
            first.model_copy(update={"identities": Identities(parameter_prefix="changed__")}),
        ),
    ]
    for write in writes:
        with pytest.raises(Unavailable):
            write()
        assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
