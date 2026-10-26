from __future__ import annotations

import uuid

from ecosemantic.model.canonical import (
    base_pin,
    canonical,
    canonical_model,
    content_hash,
    significant,
)
from ecosemantic.model.entities import Case, ProductSystem


def test_hash_is_sha256_hex(product_system: ProductSystem) -> None:
    assert len(content_hash(product_system)) == 64


def test_comments_ids_and_metadata_do_not_change_the_hash(product_system: ProductSystem) -> None:
    before = content_hash(product_system)
    other = product_system.model_copy(deep=True)
    other.id = uuid.uuid4()
    other.notes = "different"
    other.processes[0].comment = "different"
    other.processes[0].metadata["life_cycle_stage"] = "use_phase"
    other.processes[0].exchanges[1].comment = "different"
    other.processes[0].exchanges[1].id = uuid.uuid4()
    assert content_hash(other) == before


def test_amount_formula_and_uncertainty_change_the_hash(product_system: ProductSystem) -> None:
    before = content_hash(product_system)
    amount = product_system.model_copy(deep=True)
    amount.processes[1].exchanges[3].amount = 40.0
    assert content_hash(amount) != before
    formula = product_system.model_copy(deep=True)
    formula.processes[0].exchanges[1].formula = "fabric_mass * 2"
    assert content_hash(formula) != before
    unc = product_system.model_copy(deep=True)
    unc.processes[1].exchanges[1].uncertainty = None
    assert content_hash(unc) != before


def test_parameters_and_cases_change_the_hash(product_system: ProductSystem) -> None:
    before = content_hash(product_system)
    param = product_system.model_copy(deep=True)
    param.parameters[1].value = 0.12
    assert content_hash(param) != before
    case = product_system.model_copy(deep=True)
    case.cases[0].values["fabric_mass"] = 0.16
    assert content_hash(case) != before


def test_order_is_excluded(product_system: ProductSystem) -> None:
    before = content_hash(product_system)
    reordered = product_system.model_copy(deep=True)
    reordered.processes.reverse()
    reordered.processes[-1].exchanges.reverse()
    assert content_hash(reordered) == before


def test_every_process_is_hashed(product_system: ProductSystem) -> None:
    before = content_hash(product_system)
    changed = product_system.model_copy(deep=True)
    changed.process("organic_yarn").exchanges[1].amount = 9.0
    assert content_hash(changed) != before


def test_two_documents_differing_only_in_the_reference_process_hash_differently(
    product_system: ProductSystem,
) -> None:
    other = product_system.model_copy(update={"reference_process": "fabric"})
    unset = product_system.model_copy(update={"reference_process": None})
    hashes = {content_hash(product_system), content_hash(other), content_hash(unset)}
    assert len(hashes) == 3


def test_canonical_shape(product_system: ProductSystem) -> None:
    processes, exchanges, parameters, cases, reference = canonical(product_system)
    assert reference == [{"reference_process": "tshirt"}]
    assert [a["code"] for a in processes] == ["fabric", "organic_yarn", "tshirt", "yarn"]
    assert len(exchanges) == 17
    # the organic yarn's amount of 0 sorts first
    assert exchanges[0]["process"] == "fabric"
    assert {e["amount"] for e in exchanges if e["type"] == "production"} == {"1"}
    assert parameters[0]["name"] == "elec_per_kg"
    assert cases[0]["values"] == {"fabric_mass": "0.25"}


def test_the_canonical_model_is_the_processes_and_the_exchanges(
    product_system: ProductSystem,
) -> None:
    processes, exchanges, _, _, _ = canonical(product_system)
    assert canonical_model(product_system) == [processes, exchanges]
    edited = product_system.model_copy(deep=True)
    edited.parameters[0].value = 99.0
    assert canonical_model(edited) == canonical_model(product_system)


def test_a_number_is_compared_at_twelve_significant_digits() -> None:
    assert significant(0.1 + 0.2) == "0.3"
    assert significant(1234567.123456789) == "1234567.12346"


def test_the_base_pin_leaves_the_cases_out_and_moves_with_the_model(
    product_system: ProductSystem,
) -> None:
    before = base_pin(product_system)
    assert before != content_hash(product_system)
    added = product_system.model_copy(deep=True)
    added.cases.append(Case(name="medium", values={"fabric_mass": 0.2}))
    changed = product_system.model_copy(deep=True)
    changed.cases[0].values["fabric_mass"] = 0.1
    deleted = product_system.model_copy(deep=True)
    deleted.cases.pop()
    assert {base_pin(added), base_pin(changed), base_pin(deleted)} == {before}
    edited = product_system.model_copy(deep=True)
    edited.process("fabric").exchanges[2].amount = 3.0
    assert base_pin(edited) != before


def test_a_named_build_enters_the_hash_and_the_base_pin(product_system: ProductSystem) -> None:
    # a system naming no build keeps the projection it has without one
    assert canonical(product_system)[-1] == [{"reference_process": "tshirt"}]
    builds = [
        product_system.model_copy(
            update={"database": product_system.database.model_copy(update={"fingerprint": f})}
        )
        for f in ("a" * 64, "b" * 64)
    ]
    assert canonical(builds[0])[-1] == [{"reference_process": "tshirt", "fingerprint": "a" * 64}]
    assert len({content_hash(product_system), *(content_hash(b) for b in builds)}) == 3
    assert len({base_pin(product_system), *(base_pin(b) for b in builds)}) == 3
