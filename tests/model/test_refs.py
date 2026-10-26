from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from ecosemantic.model.refs import (
    BackgroundRef,
    ElementaryFlowRef,
    ExchangeInput,
    ForegroundRef,
    keygen,
    olca_elementary_flow_id,
    olca_process_id,
    olca_product_flow_id,
    slug,
    split_native_id,
)

ACTIVITY = "ccc3b9d2-b743-5b01-b794-8fa832c3d234"
PRODUCT = "00cf27fa-922c-54a8-890b-766f5c7895f9"
FLOW = "f276ca83-6438-5672-a5c7-9b17af72bb8a"
NATIVE = f"{ACTIVITY}_{PRODUCT}"


def test_keygen_matches_java_name_uuid() -> None:
    # values from java.util.UUID.nameUUIDFromBytes on the same lowercased path
    assert keygen(ACTIVITY, PRODUCT) == "676a9fb1-f606-3aea-be98-98bc0a933c8c"
    assert keygen("CH") == "d88fc6ed-f21e-3464-935f-f76288b84103"


def test_olca_ids_for_ecoinvent() -> None:
    assert olca_process_id("ecoinvent", NATIVE) == keygen(ACTIVITY, PRODUCT)
    assert olca_product_flow_id("ecoinvent", NATIVE) == PRODUCT
    assert olca_elementary_flow_id("ecoinvent", FLOW) == FLOW


OLCA_PROCESS = "a7c3c6f0-1c2e-4a0b-9b4f-2d0e3f6a7b8c"
OLCA_FLOW = "0f1e2d3c-4b5a-4968-8776-655443322110"
OLCA_NATIVE = f"{OLCA_PROCESS}_{OLCA_FLOW}"


def test_olca_scheme_splits_process_and_product_flow() -> None:
    # a USLCI process with several products is several references, one per product flow
    assert olca_process_id("olca", OLCA_NATIVE) == OLCA_PROCESS
    assert olca_product_flow_id("olca", OLCA_NATIVE) == OLCA_FLOW
    with pytest.raises(ValueError):
        olca_process_id("olca", OLCA_PROCESS)


def test_elementary_flow_id_uses_mapping_when_present() -> None:
    assert olca_elementary_flow_id("ecoinvent", "x", {"x": "y"}) == "y"
    assert olca_elementary_flow_id("ecoinvent", "z", {"x": "y"}) == "z"


def test_split_rejects_malformed_id() -> None:
    with pytest.raises(ValueError):
        split_native_id("not-an-id")


def test_exchange_input_discriminates_on_kind() -> None:
    adapter = TypeAdapter(ExchangeInput)
    assert isinstance(adapter.validate_python({"kind": "foreground", "code": "x"}), ForegroundRef)
    assert isinstance(
        adapter.validate_python({"kind": "background", "database": "d", "id": NATIVE}),
        BackgroundRef,
    )
    assert isinstance(
        adapter.validate_python({"kind": "elementary_flow", "database": "b", "id": "f"}),
        ElementaryFlowRef,
    )


def test_refs_are_frozen_and_hashable() -> None:
    assert len({ForegroundRef(code="a"), ForegroundRef(code="a")}) == 1


def test_a_slug_keeps_letters_and_digits_and_joins_the_rest_with_the_separator() -> None:
    assert slug("Battery pack (NMC)", "-") == "battery-pack-nmc"
    assert slug("Battery pack (NMC)", "_") == "battery_pack_nmc"
    assert slug("  --  ", "-") == ""
