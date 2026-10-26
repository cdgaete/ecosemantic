from __future__ import annotations

import uuid

import pytest

from ecosemantic.compute.edits import (
    add_exchange,
    add_process,
    add_scenario,
    new_product_system,
    patch_exchange,
    patch_process,
    patch_product_system,
    rebase_database,
    rebase_links,
    rebase_scenario,
    remove_exchange,
    remove_process,
    remove_scenario,
    set_parameter_space,
)
from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.canonical import base_pin, content_hash
from ecosemantic.model.entities import (
    Case,
    ExchangeOverride,
    Parameter,
    ParameterOverride,
    ProductSystem,
    Scenario,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
)
from tests.conftest import CO2, COTTON, DATABASE, EI, ORGANIC, frame_system, widget_linking


def test_new_product_system_is_empty_and_unhashed() -> None:
    system = new_product_system("bottle", DATABASE, "one bottle", "")
    assert system.name == "bottle" and system.database == DATABASE
    assert system.processes == [] and system.parameters == [] and system.hash is None


def test_patch_product_system_replaces_only_what_is_given(product_system: ProductSystem) -> None:
    out = patch_product_system(product_system, notes="checked")
    assert out.notes == "checked" and out.name == product_system.name
    assert product_system.notes == "Fixture."


def test_patch_product_system_needs_a_field(product_system: ProductSystem) -> None:
    with pytest.raises(Invalid):
        patch_product_system(product_system)


def test_patch_product_system_sets_the_reference_to_a_process(
    product_system: ProductSystem,
) -> None:
    patched = patch_product_system(product_system, reference_process="fabric")
    assert patched.reference_process == "fabric"
    # the reference sets the functional unit, so the hash moves with it
    assert content_hash(patched) != content_hash(product_system)
    with pytest.raises(Invalid, match="names no process"):
        patch_product_system(product_system, reference_process="ghost")


def test_add_process_creates_its_production_exchange(product_system: ProductSystem) -> None:
    out, process = add_process(
        product_system, code="dye", name="dyeing", unit="kilogram", reference_product="dyed fabric"
    )
    assert out.process("dye") is process and process.location == "GLO"
    assert [e.type for e in process.exchanges] == ["production"]
    assert process.exchanges[0].amount == 1.0 and process.exchanges[0].unit == "kilogram"
    assert process.exchanges[0].name == "dyed fabric"
    assert set(process.metadata) == {"life_cycle_stage", "hierarchy_level", "supply_chain_tier"}
    assert len(product_system.processes) == 4


def test_add_process_refuses_a_taken_code_and_a_bad_one(product_system: ProductSystem) -> None:
    with pytest.raises(Conflict):
        add_process(product_system, code="yarn", name="x", unit="kilogram", reference_product="x")
    with pytest.raises(Invalid):
        add_process(product_system, code="a b", name="x", unit="kilogram", reference_product="x")


def test_patch_process_merges_metadata_and_clears_a_comment(
    product_system: ProductSystem,
) -> None:
    out, process = patch_process(
        product_system, "tshirt", name="t-shirt", metadata={"hierarchy_level": 5}, clear=["comment"]
    )
    assert process.name == "t-shirt" and process.comment is None
    assert process.metadata["hierarchy_level"] == 5
    assert process.metadata["life_cycle_stage"] == "manufacturing"
    assert product_system.process("tshirt").name == "cotton t-shirt, assembled"


def test_patch_process_unit_follows_only_an_unconsumed_process(
    product_system: ProductSystem,
) -> None:
    out, tshirt = patch_process(product_system, "tshirt", unit="piece")
    assert tshirt.unit == "piece" and tshirt.exchanges[0].unit == "piece"
    with pytest.raises(Invalid, match="tshirt"):
        patch_process(product_system, "fabric", unit="tonne")


def test_patch_process_needs_a_field_and_a_known_code(product_system: ProductSystem) -> None:
    with pytest.raises(Invalid):
        patch_process(product_system, "tshirt")
    with pytest.raises(NotFound):
        patch_process(product_system, "nothing", name="x")


def test_remove_process_refuses_a_consumed_or_overridden_process(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Invalid, match="tshirt"):
        remove_process(product_system, "fabric")
    # the scenario overrides the t-shirt, which is not the reference here
    moved = patch_product_system(product_system, reference_process="fabric")
    with pytest.raises(Invalid, match="organic"):
        remove_process(moved, "tshirt")


def test_remove_process_refuses_the_reference_process(product_system: ProductSystem) -> None:
    with pytest.raises(Invalid, match="'tshirt' is the reference process"):
        remove_process(product_system, "tshirt")


def test_remove_process_refuses_a_scenario_swap_target(product_system: ProductSystem) -> None:
    system = product_system.model_copy(deep=True)
    # the fabric's organic input goes, so only the scenario holds the organic yarn
    system.process("fabric").exchanges.pop()
    system.scenarios.append(
        Scenario(
            name="organic_swap",
            overrides=[
                ExchangeOverride(
                    exchange_id=system.process("fabric").exchanges[1].id,
                    input=ForegroundRef(code="organic_yarn"),
                )
            ],
        )
    )
    with pytest.raises(Invalid, match="organic_swap"):
        remove_process(system, "organic_yarn")


def test_remove_process_removes_a_free_one(product_system: ProductSystem) -> None:
    system = product_system.model_copy(deep=True)
    system.process("fabric").exchanges.pop()
    out = remove_process(system, "organic_yarn")
    assert [a.code for a in out.processes] == ["tshirt", "fabric", "yarn"]
    assert len(product_system.processes) == 4


def test_add_exchange_to_a_foreground_provider_takes_its_unit_and_name(
    product_system: ProductSystem,
) -> None:
    out, exchange = add_exchange(
        product_system, "tshirt", type="product", input=ForegroundRef(code="yarn"), amount=0.1
    )
    assert exchange.unit == "kilogram" and exchange.name == "cotton yarn"
    assert exchange in out.process("tshirt").exchanges
    with pytest.raises(Invalid, match="kilogram"):
        add_exchange(
            product_system,
            "tshirt",
            type="product",
            input=ForegroundRef(code="yarn"),
            amount=0.1,
            unit="tonne",
        )


def test_add_exchange_checks_the_input_against_the_type(product_system: ProductSystem) -> None:
    with pytest.raises(Invalid):
        add_exchange(product_system, "tshirt", type="production", amount=1.0)
    with pytest.raises(Invalid):
        add_exchange(product_system, "tshirt", type="product", amount=1.0)
    with pytest.raises(Invalid):
        add_exchange(product_system, "tshirt", type="elementary", input=COTTON, amount=1.0)
    with pytest.raises(NotFound):
        add_exchange(
            product_system,
            "tshirt",
            type="product",
            input=ForegroundRef(code="nothing"),
            amount=1.0,
        )


def test_add_exchange_to_a_background_needs_resolved_values_on_this_database(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Invalid, match="unit"):
        add_exchange(product_system, "yarn", type="product", input=COTTON, amount=1.0)
    other = BackgroundRef(database="ecoinvent-3.10-cutoff", id=COTTON.id)
    with pytest.raises(Invalid, match=EI):
        add_exchange(
            product_system,
            "yarn",
            type="product",
            input=other,
            amount=1.0,
            unit="kilogram",
            name="fibre",
        )
    out, exchange = add_exchange(
        product_system,
        "yarn",
        type="product",
        input=COTTON,
        amount=1.0,
        unit="kilogram",
        name="cotton fibre",
    )
    assert exchange.input == COTTON and exchange.name == "cotton fibre"
    with pytest.raises(Invalid):
        add_exchange(
            product_system,
            "yarn",
            type="elementary",
            input=ElementaryFlowRef(database="other-biosphere", id=CO2.id),
            amount=1.0,
            unit="kilogram",
            name="CO2",
        )


def test_add_exchange_with_a_formula_stores_its_value(product_system: ProductSystem) -> None:
    out, exchange = add_exchange(
        product_system,
        "tshirt",
        type="product",
        input=ForegroundRef(code="yarn"),
        formula="fabric_mass * 2",
    )
    assert exchange.formula == "fabric_mass * 2" and exchange.amount == pytest.approx(0.4)
    with pytest.raises(Invalid):
        add_exchange(
            product_system,
            "tshirt",
            type="product",
            input=ForegroundRef(code="yarn"),
            formula="no_such_parameter",
        )
    with pytest.raises(Invalid):
        add_exchange(
            product_system,
            "tshirt",
            type="product",
            input=ForegroundRef(code="yarn"),
            amount=1.0,
            formula="fabric_mass",
        )


def test_add_exchange_allows_one_production_and_a_foreground_input(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Invalid, match="production"):
        add_exchange(product_system, "tshirt", type="production", amount=2.0)
    added, _ = add_process(
        product_system,
        code="organic_fabric",
        name="organic fabric",
        unit="kilogram",
        reference_product="organic fabric",
    )
    out, exchange = add_exchange(
        added,
        "organic_fabric",
        type="product",
        input=ForegroundRef(code="organic_yarn"),
        amount=1.1,
    )
    assert exchange.unit == "kilogram" and exchange.name == "organic cotton yarn"


def test_patch_exchange_respects_a_formula_until_it_is_cleared(
    product_system: ProductSystem,
) -> None:
    fabric_in = product_system.process("tshirt").exchanges[1]
    with pytest.raises(Invalid, match="formula"):
        patch_exchange(product_system, fabric_in.id, amount=0.3)
    out, exchange = patch_exchange(product_system, fabric_in.id, amount=0.3, clear=["formula"])
    assert exchange.formula is None and exchange.amount == 0.3
    out, exchange = patch_exchange(product_system, fabric_in.id, formula="fabric_mass * 3")
    assert exchange.amount == pytest.approx(0.6)


def test_patch_exchange_units_follow_the_provider(product_system: ProductSystem) -> None:
    tshirt = product_system.process("tshirt")
    with pytest.raises(Invalid, match="process"):
        patch_exchange(product_system, tshirt.exchanges[0].id, unit="piece")
    with pytest.raises(Invalid, match="kilogram"):
        patch_exchange(product_system, tshirt.exchanges[1].id, unit="tonne")
    out, exchange = patch_exchange(
        product_system, tshirt.exchanges[3].id, comment=None, clear=["comment", "uncertainty"]
    )
    assert exchange.comment is None and exchange.uncertainty is None
    with pytest.raises(Invalid):
        patch_exchange(product_system, tshirt.exchanges[3].id)
    with pytest.raises(NotFound):
        patch_exchange(product_system, uuid.uuid4(), name="x")


def test_remove_exchange_refuses_an_overridden_one(product_system: ProductSystem) -> None:
    tshirt = product_system.process("tshirt")
    elec = tshirt.exchanges[2]
    with pytest.raises(Invalid) as caught:
        remove_exchange(product_system, elec.id)
    message = str(caught.value)
    assert f"sewing electricity (cotton t-shirt, assembled) {elec.id}" in message
    assert "'organic'" in message
    out = remove_exchange(product_system, tshirt.exchanges[4].id)
    assert len(out.process("tshirt").exchanges) == 4 and len(tshirt.exchanges) == 5


def test_remove_exchange_refuses_a_production_exchange(product_system: ProductSystem) -> None:
    production = product_system.process("tshirt").exchanges[0]
    assert production.type == "production"
    with pytest.raises(Invalid, match="keeps its production exchange"):
        remove_exchange(product_system, production.id)


def test_set_parameter_space_replaces_by_name_and_materialises(
    product_system: ProductSystem,
) -> None:
    out = set_parameter_space(
        product_system, parameters=[Parameter(name="fabric_mass", value=0.3, unit="kilogram")]
    )
    assert out.process("tshirt").exchanges[1].amount == pytest.approx(0.3)
    assert product_system.process("tshirt").exchanges[1].amount == 0.2
    assert [p.name for p in out.parameters] == [p.name for p in product_system.parameters]


def test_set_parameter_space_refuses_deleting_a_used_parameter(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Invalid, match="fibre_mass"):
        set_parameter_space(product_system, delete_parameters=["waste_rate"])
    with pytest.raises(Invalid, match="tshirt"):
        set_parameter_space(product_system, delete_parameters=["elec_per_kg"])
    with pytest.raises(Invalid, match="small"):
        set_parameter_space(
            product_system, delete_parameters=["fabric_mass"], delete_cases=["large"]
        )
    with pytest.raises(NotFound):
        set_parameter_space(product_system, delete_parameters=["nothing"])


def test_set_parameter_space_drops_a_parameter_with_its_last_user_in_one_call(
    product_system: ProductSystem,
) -> None:
    out = set_parameter_space(
        product_system,
        cases=[Case(name="small", values={"fabric_mass": 0.15})],
        delete_parameters=["waste_rate", "fibre_mass"],
        delete_cases=["large"],
    )
    assert [p.name for p in out.parameters] == ["fabric_mass", "elec_per_kg", "organic_share"]
    assert [c.name for c in out.cases] == ["small"]


def test_set_parameter_space_adds_then_removes_a_free_parameter(
    product_system: ProductSystem,
) -> None:
    added = set_parameter_space(product_system, parameters=[Parameter(name="spare", value=1.0)])
    assert "spare" in {p.name for p in added.parameters}
    removed = set_parameter_space(added, delete_parameters=["spare"])
    assert "spare" not in {p.name for p in removed.parameters}


def test_set_parameter_space_cases_name_literal_parameters_only(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Invalid, match="fibre_mass"):
        set_parameter_space(product_system, cases=[Case(name="x", values={"fibre_mass": 1.0})])
    with pytest.raises(Invalid, match="nothing"):
        set_parameter_space(product_system, cases=[Case(name="x", values={"nothing": 1.0})])
    out = set_parameter_space(
        product_system,
        cases=[Case(name="small", values={"fabric_mass": 0.12})],
        delete_cases=["large"],
    )
    assert {c.name: c.values for c in out.cases} == {"small": {"fabric_mass": 0.12}}
    with pytest.raises(NotFound):
        set_parameter_space(product_system, delete_cases=["nothing"])
    with pytest.raises(Invalid):
        set_parameter_space(product_system)


def test_add_scenario_pins_the_base_and_dry_runs(product_system: ProductSystem) -> None:
    elec = product_system.process("tshirt").exchanges[2]
    out, scenario = add_scenario(
        product_system,
        name="half_elec",
        description="",
        overrides=[ExchangeOverride(exchange_id=elec.id, multiplier=0.5)],
    )
    assert scenario.base_hash == base_pin(product_system)
    assert [s.name for s in out.scenarios] == ["organic", "half_elec"]
    with pytest.raises(Conflict):
        add_scenario(product_system, name="organic", description="", overrides=scenario.overrides)
    with pytest.raises(Invalid):
        add_scenario(product_system, name="empty", description="", overrides=[])
    with pytest.raises(NotFound):
        add_scenario(
            product_system,
            name="lost",
            description="",
            overrides=[ExchangeOverride(exchange_id=uuid.uuid4(), amount=1.0)],
        )
    with pytest.raises(Invalid, match="derived"):
        add_scenario(
            product_system,
            name="derived",
            description="",
            overrides=[ParameterOverride(name="fibre_mass", value=1.0)],
        )


def test_a_case_takes_no_scenario_name_and_a_scenario_no_case_name(
    product_system: ProductSystem,
) -> None:
    with pytest.raises(Conflict, match=r"\['organic'\] name scenarios"):
        set_parameter_space(
            product_system, cases=[Case(name="organic", values={"fabric_mass": 0.2})]
        )
    elec = product_system.process("tshirt").exchanges[2]
    with pytest.raises(Conflict, match="case 'small' exists"):
        add_scenario(
            product_system,
            name="small",
            description="",
            overrides=[ExchangeOverride(exchange_id=elec.id, multiplier=0.5)],
        )


def test_remove_and_rebase_a_scenario(product_system: ProductSystem) -> None:
    out = remove_scenario(product_system, "organic")
    assert out.scenarios == [] and len(product_system.scenarios) == 1
    with pytest.raises(NotFound):
        remove_scenario(product_system, "nothing")
    changed = set_parameter_space(
        product_system, parameters=[Parameter(name="fabric_mass", value=0.3, unit="kilogram")]
    )
    rebased, scenario = rebase_scenario(changed, "organic")
    assert scenario.base_hash == base_pin(changed)
    assert product_system.scenarios[0].base_hash == base_pin(product_system)


def test_a_link_takes_the_unit_and_product_of_the_linked_reference_process() -> None:
    frame = frame_system()
    frame = frame.model_copy(update={"hash": content_hash(frame)})
    host = widget_linking(frame)
    link = SystemRef(product_system_id=frame.id, at_hash=frame.hash)
    out, exchange = add_exchange(
        host, "widget", type="product", input=link, amount=1.0, linked=frame
    )
    assert (exchange.unit, exchange.name, exchange.input) == ("kilogram", "frame", link)
    elsewhere = frame.model_copy(
        update={"database": frame.database.model_copy(update={"name": "other"})}
    )
    for linked, reason in (
        (None, "as it stood at the pin"),
        (elsewhere, "is on 'other'"),
        (frame.model_copy(update={"reference_process": None}), "no reference process"),
    ):
        with pytest.raises(Invalid, match=reason):
            add_exchange(host, "widget", type="product", input=link, amount=1.0, linked=linked)
    with pytest.raises(Invalid, match="cannot link itself"):
        add_exchange(
            host,
            "widget",
            type="product",
            input=SystemRef(product_system_id=host.id, at_hash="a" * 64),
            amount=1.0,
            linked=host,
        )


def test_rebase_links_moves_each_pin_behind_its_systems_current_hash() -> None:
    frame = frame_system()
    host = widget_linking(frame)
    moved, refs = rebase_links(host, {frame.id: "b" * 64})
    assert refs == [SystemRef(product_system_id=frame.id, at_hash="b" * 64)]
    assert moved.process("widget").exchanges[3].input == refs[0]
    assert content_hash(moved) != content_hash(host)
    with pytest.raises(Invalid, match="current"):
        rebase_links(host, {frame.id: content_hash(frame)})


def test_rebase_links_to_one_system_leaves_the_others_and_names_each_pin_once() -> None:
    frame = frame_system()
    host = widget_linking(frame)
    widget = host.process("widget")
    other = SystemRef(product_system_id=uuid.uuid4(), at_hash="c" * 64)
    widget.exchanges += [
        widget.exchanges[3].model_copy(update={"id": uuid.uuid4()}),
        widget.exchanges[3].model_copy(update={"id": uuid.uuid4(), "input": other}),
    ]
    current = {frame.id: "b" * 64, other.product_system_id: "d" * 64}
    moved, refs = rebase_links(host, current, linked=frame.id)
    assert refs == [SystemRef(product_system_id=frame.id, at_hash="b" * 64)]
    exchanges = moved.process("widget").exchanges
    assert [exchanges[3].input, exchanges[5].input, exchanges[6].input] == [refs[0], refs[0], other]


def test_rebase_links_to_a_system_it_does_not_link_says_so() -> None:
    host = widget_linking(frame_system())
    stranger = uuid.uuid4()
    with pytest.raises(Invalid, match=f"widget_linking has no link to product system {stranger}"):
        rebase_links(host, {}, linked=stranger)


def test_rebase_database_takes_the_installed_build(product_system: ProductSystem) -> None:
    installed = product_system.database.model_copy(update={"fingerprint": "a" * 64})
    moved = rebase_database(product_system, installed)
    assert moved.database == installed and moved.processes == product_system.processes
    assert content_hash(moved) != content_hash(product_system)
    with pytest.raises(Invalid, match=f"is on build aaaaaaaaaaaa of {EI!r} already"):
        rebase_database(moved, installed)


def test_rebase_database_onto_another_database_renames_every_reference(
    product_system: ProductSystem,
) -> None:
    other = Database(
        name="other",
        elementary_flows="other-biosphere",
        scheme="olca",
        version="2",
        system_model="cutoff",
        fingerprint="b" * 64,
    )
    moved = rebase_database(product_system, other)
    assert moved.database == other

    def refs(system: ProductSystem) -> list[tuple[str, str, str]]:
        found = [e.input for p in system.processes for e in p.exchanges if e.input is not None]
        found += [
            o.input
            for s in system.scenarios
            for o in s.overrides
            if isinstance(o, ExchangeOverride) and o.input is not None
        ]
        return [(r.kind, getattr(r, "database", ""), getattr(r, "id", "")) for r in found]

    before, after = refs(product_system), refs(moved)
    assert [(k, i) for k, _, i in after] == [(k, i) for k, _, i in before]
    assert {d for k, d, _ in after if k == "background"} == {"other"}
    assert {d for k, d, _ in after if k == "elementary_flow"} == {"other-biosphere"}
    # the scenario's swap to a background dataset names the new database too
    assert ("background", "other", ORGANIC.id) in after
