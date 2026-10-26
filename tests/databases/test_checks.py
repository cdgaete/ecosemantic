"""The structural check a source's import is held to: every factor names a flow of the import and
every technosphere row a dataset of it."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ecosemantic.databases.checks import unnamed
from ecosemantic.databases.uslci.build import build
from ecosemantic.package.background import Import, read_background
from tests.databases.uslci_fixture import (
    INVENTORY_NAME,
    METHOD_NAME,
    write_inventory,
    write_method,
)

VERSION = "1.2026-09.0"
ABSENT = "a-flow-and-a-dataset-the-import-lacks"


@pytest.fixture
def imported(tmp_path: Path) -> Import:
    """The fixture's release built into a bundle and read back by the core's importer."""
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    built = build(inventory, (method,), version=VERSION, out_dir=tmp_path / "out")
    return read_background(built.bundle, built.bundle.stem, foreground=frozenset())


def test_the_fixture_s_import_names_a_flow_and_a_dataset_everywhere(imported: Import) -> None:
    assert unnamed(imported) == []


def test_a_factor_naming_a_flow_the_import_lacks_is_named(imported: Import) -> None:
    method = imported.methods[0]
    factors = [*method.factors, (("elementary flows", ABSENT), 1.0)]
    broken = replace(imported, methods=[replace(method, factors=factors)])
    assert unnamed(broken) == [
        f"{method.key[1]}, {method.key[2]} names flow {ABSENT}, which the import lacks"
    ]


def test_a_link_naming_a_dataset_the_import_lacks_is_named(imported: Import) -> None:
    key, dataset = next(iter(imported.datasets.items()))
    rows = [
        *dataset["exchanges"],
        {"input": ("technosphere flows", ABSENT), "type": "technosphere"},
    ]
    datasets = {**imported.datasets, key: {**dataset, "exchanges": rows}}
    assert unnamed(replace(imported, datasets=datasets)) == [
        f"{key[1]} takes {ABSENT}, which is no dataset of the import"
    ]
