from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, Exchange, ProductSystem
from ecosemantic.package.log import (
    diff_product_systems,
    next_entry,
    read_log,
    verify_chain,
    write_log,
)
from tests.conftest import CO2

AGENT = Actor(kind="agent", id="claude")


def test_diff_from_nothing_is_one_add(product_system: ProductSystem) -> None:
    changes = diff_product_systems(None, product_system)
    assert [c.op for c in changes] == ["add"]
    assert changes[0].entity == "product_system"


def test_diff_reports_entity_level_changes(product_system: ProductSystem) -> None:
    after = product_system.model_copy(deep=True)
    after.processes[1].name = "cotton fabric, woven"
    after.processes[1].exchanges[3].amount = 40.0
    after.processes[2].exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="elementary",
            name="Carbon dioxide, fossil",
            amount=0.002,
            unit="kilogram",
            input=CO2,
        )
    )
    after.parameters[1].value = 0.12
    del after.cases[1]
    changes = diff_product_systems(product_system, after)
    keys = {(c.op, c.entity, c.field) for c in changes}
    assert ("update", "process", "name") in keys
    assert ("update", "exchange", "amount") in keys
    assert ("add", "exchange", None) in keys
    assert ("update", "parameter", "value") in keys
    assert ("delete", "case", None) in keys
    assert len(changes) == 5
    amount = next(c for c in changes if c.entity == "exchange" and c.op == "update")
    assert amount.before == 50.0 and amount.after == 40.0


def test_entries_chain_on_hashes(product_system: ProductSystem) -> None:
    now = datetime(2000, 1, 1, tzinfo=UTC)
    first = next_entry([], AGENT, "mcp", None, product_system, "created", now)
    assert first.seq == 1 and first.base_hash is None
    assert first.result_hash == content_hash(product_system)
    after = product_system.model_copy(deep=True)
    after.parameters[1].value = 0.12
    second = next_entry([first], AGENT, "mcp", product_system, after, "waste rate", now)
    assert second.seq == 2 and second.base_hash == first.result_hash
    verify_chain([first, second])
    with pytest.raises(Invalid):
        verify_chain([first, second.model_copy(update={"base_hash": "0" * 64})])
    with pytest.raises(Invalid):
        next_entry([first], AGENT, "mcp", after, after, "stale", now)


def test_log_round_trips_through_jsonl(product_system: ProductSystem, tmp_path: Path) -> None:
    entry = next_entry([], AGENT, "mcp", None, product_system, "created")
    write_log(tmp_path, [entry])
    assert (tmp_path / "ecosemantic" / "log.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert read_log(tmp_path) == [entry]
    assert read_log(tmp_path / "missing") == []
