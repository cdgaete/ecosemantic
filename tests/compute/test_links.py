from __future__ import annotations

import uuid

import pytest

from ecosemantic.compute.links import (
    closure,
    held_pins,
    link_pin,
    linked_documents,
    pinning,
    pins,
)
from ecosemantic.compute.overrides import case_pin
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import Actor, Case, Exchange, Parameter, Process, ProductSystem
from ecosemantic.model.refs import SystemRef
from tests.conftest import DATABASE, frame_system, widget_linking
from tests.memory_storage import MemoryStorage


def _system(name: str, *links: SystemRef) -> ProductSystem:
    """A one-process system named `name`, taking one unit of each linked system."""
    process = Process(
        id=uuid.uuid5(uuid.NAMESPACE_OID, name),
        code="p",
        name=name,
        unit="unit",
        location="GLO",
        reference_product=name,
        exchanges=[
            Exchange(id=uuid.uuid4(), type="production", name=name, amount=1.0, unit="unit"),
            *(
                Exchange(
                    id=uuid.uuid4(), type="product", name="in", amount=1.0, unit="unit", input=link
                )
                for link in links
            ),
        ],
    )
    system = ProductSystem(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        database=DATABASE,
        processes=[process],
        reference_process="p",
    )
    return system.model_copy(update={"hash": content_hash(system)})


def _cased(name: str, *links: SystemRef) -> ProductSystem:
    """A one-process system whose production a parameter sets, with a case doubling it."""
    system = _system(name, *links)
    system.process("p").exchanges[0].formula = "made"
    system.parameters = [Parameter(name="made", value=1.0)]
    system.cases = [
        Case(name="double", values={"made": 2.0}),
        Case(name="triple", values={"made": 3.0}),
    ]
    return system.model_copy(update={"hash": content_hash(system)})


def _link(system: ProductSystem, case: str | None = None) -> SystemRef:
    return SystemRef(product_system_id=system.id, at_hash=system.hash, case=case)


def _reader(*systems: ProductSystem):
    held = {(s.id, s.hash): s for s in systems}

    async def read(product_system_id: uuid.UUID, at_hash: str) -> ProductSystem:
        return held[(product_system_id, at_hash)]

    return read


async def test_the_closure_reads_each_linked_system_at_its_pin_through_the_links() -> None:
    c = _system("c")
    b = _system("b", _link(c))
    a = _system("a", _link(b), _link(b))
    assert pins(a) == [_link(b)]
    found = await closure(a, _reader(b, c))
    assert found.documents == {b.id: b, c.id: c}
    assert found.reached_from == {b.id: a.id, c.id: b.id}


async def test_a_system_two_links_reach_at_one_pin_is_read_once() -> None:
    c = _system("c")
    b = _system("b", _link(c))
    a = _system("a", _link(b), _link(c))
    read = _reader(b, c)
    names: list[str] = []

    async def counted(product_system_id: uuid.UUID, at_hash: str) -> ProductSystem:
        document = await read(product_system_id, at_hash)
        names.append(document.name)
        return document

    found = await closure(a, counted)
    assert found.documents == {b.id: b, c.id: c}
    # a reaches c before b does
    assert found.reached_from == {b.id: a.id, c.id: a.id}
    assert names == ["b", "c"]


async def test_a_link_back_to_the_root_is_refused_naming_the_chain() -> None:
    a = _system("a")
    b = _system("b", _link(a))
    root = _system("a", _link(b))
    with pytest.raises(Invalid, match="a → b → a"):
        await closure(root, _reader(b))


async def test_one_system_reached_at_two_hashes_is_refused() -> None:
    c_old = _system("c")
    c_new = c_old.model_copy(update={"hash": "f" * 64})
    b = _system("b", _link(c_old))
    a = _system("a", _link(b), _link(c_new))
    with pytest.raises(Invalid, match="rebase_links"):
        await closure(a, _reader(b, c_old, c_new))


def test_pinning_names_the_systems_whose_links_name_a_system() -> None:
    b = _system("b")
    a = _system("a", _link(b))
    assert pinning(b.id, [a, b]) == ["a"]
    assert pinning(a.id, [a, b]) == []


async def test_a_linked_system_is_materialised_under_the_case_its_link_names() -> None:
    c = _cased("c")
    a = _system("a", _link(c, "double"))
    [linked] = (await linked_documents(a, _reader(c))).values()
    assert linked.process("p").exchanges[0].amount == 2.0
    plain = _system("a", _link(c))
    [unnamed] = (await linked_documents(plain, _reader(c))).values()
    assert unnamed.process("p").exchanges[0].amount == 1.0


async def test_a_link_naming_a_case_its_system_does_not_carry_is_not_found() -> None:
    c = _cased("c")
    a = _system("a", _link(c, "ghost"))
    with pytest.raises(NotFound, match="ghost"):
        await linked_documents(a, _reader(c))


async def test_one_system_reached_under_two_cases_is_refused_naming_both_links() -> None:
    c = _cased("c")
    b = _system("b", _link(c, "double"))
    a = _system("a", _link(b), _link(c, "triple"))
    with pytest.raises(Invalid, match="double.*triple|triple.*double") as caught:
        await closure(a, _reader(b, c))
    assert "'a'" in str(caught.value) and "'b'" in str(caught.value)


def test_a_link_naming_a_case_pins_that_case() -> None:
    c = _cased("c")
    assert link_pin(c, _link(c)) == base_pin(c)
    assert link_pin(c, _link(c, "double")) == case_pin(c, c.case("double"))
    assert link_pin(c, _link(c, "double")) != link_pin(c, _link(c, "triple"))


def test_pinning_under_a_case_names_the_systems_whose_links_name_that_case() -> None:
    c = _cased("c")
    a = _system("a", _link(c, "double"))
    b = _system("b", _link(c))
    assert pinning(c.id, [a, b]) == ["a", "b"]
    assert pinning(c.id, [a, b], "double") == ["a"]
    assert pinning(c.id, [a, b], "triple") == []


def test_a_link_naming_a_case_its_document_does_not_carry_pins_nothing() -> None:
    c = _cased("c")
    assert link_pin(c, _link(c, "ghost")) is None


async def test_held_pins_name_what_the_store_holds_for_each_link() -> None:
    agent = Actor(kind="agent", id="claude")
    storage = MemoryStorage()
    frame = frame_system()
    await storage.put_product_system(frame, agent, "created")
    stored = await storage.get_product_system(frame.id)
    widget = widget_linking(stored)
    pins_held = await held_pins(widget, storage)
    assert [(p.name, p.current, p.document is not None) for p in pins_held] == [
        ("frame", base_pin(stored), True)
    ]
    await storage.delete_product_system(frame.id, agent)
    assert [p.name for p in await held_pins(widget, storage)] == [None]
