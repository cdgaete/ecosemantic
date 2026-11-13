from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from ecosemantic.errors import (
    Conflict,
    EcoSemanticError,
    Invalid,
    NotFound,
    NotSupported,
    Unavailable,
)
from ecosemantic.model.entities import Actor, DemandItem, ProductSystem
from ecosemantic.model.refs import ElementaryFlowRef, ForegroundRef
from ecosemantic.ports.resolver import FlowInfo
from ecosemantic.ports.types import (
    FLOW_TYPES,
    Account,
    Change,
    Compartment,
    DatabaseSource,
    ElementaryFlow,
    Install,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    InstallStatus,
    InstallTerms,
    InventoryRow,
    LogEntry,
    MonteCarloConfig,
    Page,
    Run,
    RunPatch,
    RunStatus,
    SourceName,
    System,
    TreeNode,
    flow_side,
    fraction_of,
    is_open,
    listed,
    page_start,
    patched,
    source_credential,
)


def test_errors_share_a_base() -> None:
    for error in (NotFound, Invalid, Conflict, Unavailable, NotSupported):
        assert issubclass(error, EcoSemanticError)


def test_page_is_generic() -> None:
    page = Page[int](items=[1, 2], has_more=True, next_cursor="2")
    assert page.items == [1, 2]
    assert Page[str](items=[], has_more=False).next_cursor is None


def test_monte_carlo_config_bounds() -> None:
    MonteCarloConfig()
    with pytest.raises(ValidationError):
        MonteCarloConfig(n_min=10, n_max=5)
    with pytest.raises(ValidationError):
        MonteCarloConfig(scope="all")


def test_tree_node_nests() -> None:
    leaf = TreeNode(
        ref=ForegroundRef(code="a"), name="a", location="GLO", score=1.0, fraction=1.0, level=1
    )
    root = TreeNode(
        ref=ForegroundRef(code="r"),
        name="r",
        location="GLO",
        score=1.0,
        fraction=1.0,
        level=0,
        children=[leaf],
    )
    assert root.children[0].name == "a"


def test_log_entry_and_change() -> None:
    entry = LogEntry(
        seq=1,
        timestamp=datetime.now(UTC),
        actor=Actor(kind="agent", id="a"),
        source="mcp",
        base_hash=None,
        result_hash="x" * 64,
        changes=[Change(op="add", entity="product_system", id=str(uuid.uuid4()))],
        message="created",
    )
    assert entry.changes[0].field is None
    assert DemandItem(ref=ForegroundRef(code="a"), amount=1.0).amount == 1.0


def test_method_not_found_carries_suggestions() -> None:
    from ecosemantic.errors import MethodNotFound, NotFound
    from ecosemantic.model.entities import Method, method_id

    spec = "db > f > c > i"
    m = Method(
        id=method_id(spec),
        tuple=("db", "f", "c", "i"),
        spec=spec,
        unit="u",
        impact_method="f",
        impact_category="c",
        indicator="i",
    )
    error = MethodNotFound("db", "nothing", [m])
    assert isinstance(error, NotFound)
    assert error.suggestions == [m]
    assert "nothing" in str(error) and spec in str(error)


def test_page_start_names_the_start_or_an_offset() -> None:
    assert page_start(None, 20) == 0 and page_start("40", 20) == 40
    with pytest.raises(Invalid):
        page_start("next", 20)


def test_page_start_refuses_a_limit_below_one() -> None:
    for limit in (0, -1):
        with pytest.raises(Invalid, match="limit is at least 1"):
            page_start(None, limit)


def test_page_at_offset_points_at_the_next_page_only_when_there_is_one() -> None:
    assert Page.at_offset([1, 2], True, 4, 2).next_cursor == "6"
    assert Page.at_offset([1], False, 4, 2).next_cursor is None


def test_flow_type_is_the_closed_vocabulary_the_backends_report() -> None:
    assert set(FLOW_TYPES) == {"emission", "natural resource", "inventory indicator", "economic"}
    with pytest.raises(ValidationError):
        ElementaryFlow(
            ref=ElementaryFlowRef(database="b", id="x"),
            name="x",
            compartment="air",
            sub_compartment=None,
            unit="kilogram",
            flow_type="resource",
        )


def test_flow_side_follows_the_type_and_the_sub_compartment() -> None:
    assert flow_side("natural resource", "in water") == "input"
    assert flow_side("natural resource", None) == "input"
    assert flow_side("emission", "urban air close to ground") == "output"
    assert flow_side("inventory indicator", "resource use") == "input"
    assert flow_side("inventory indicator", "output flow") == "output"
    assert flow_side("inventory indicator", "waste") == "output"
    assert flow_side("economic", "primary production factor") == "input"


def test_flow_side_refuses_a_pair_the_table_does_not_name() -> None:
    with pytest.raises(NotSupported):
        flow_side("economic", "waste")
    with pytest.raises(NotSupported):
        flow_side("inventory indicator", None)


def test_the_carriers_serialise_their_side() -> None:
    ref = ElementaryFlowRef(database="bio", id="x")
    flow = ElementaryFlow(
        ref=ref,
        name="Water, river",
        compartment="natural resource",
        sub_compartment="in water",
        unit="cubic meter",
        flow_type="natural resource",
    )
    assert flow.side == "input" and flow.model_dump(mode="json")["side"] == "input"
    row = InventoryRow(
        flow=ref,
        name="Carbon dioxide, fossil",
        compartment="air",
        sub_compartment=None,
        flow_type="emission",
        unit="kilogram",
        amount=1.0,
    )
    assert row.model_dump(mode="json")["side"] == "output"
    assert (
        "flow_type" in InventoryRow.model_fields and "sub_compartment" in InventoryRow.model_fields
    )


def test_the_carriers_refuse_a_pair_the_table_does_not_name() -> None:
    ref = ElementaryFlowRef(database="bio", id="x")
    fields = {"name": "x", "compartment": "economic", "sub_compartment": "waste", "unit": "kg"}
    with pytest.raises(NotSupported):
        ElementaryFlow(ref=ref, flow_type="economic", **fields)
    with pytest.raises(NotSupported):
        InventoryRow(flow=ref, flow_type="economic", amount=1.0, **fields)
    with pytest.raises(NotSupported):
        FlowInfo(flow_type="economic", **fields)


def test_a_system_of_a_product_system_names_its_database(product_system: ProductSystem) -> None:
    system = System.of(product_system)
    assert system.database == product_system.database.name
    assert system.product_system is product_system


def test_a_run_patch_replaces_the_fields_it_names_and_no_others() -> None:
    run = Run(
        id=uuid.uuid4(),
        product_system_id=uuid.uuid4(),
        at_hash="0" * 64,
        config=MonteCarloConfig(),
        posted_at=datetime.now(UTC),
        pid=7,
    )
    running = RunPatch(status="running").applied_to(run)
    assert running.status == "running" and running.pid == 7
    # a field named as none is replaced by none; a field left out is kept
    assert RunPatch(pid=None).applied_to(run).pid is None
    assert run.status == "queued" and run.pid == 7


def test_a_run_answers_its_cancellation_only_while_it_is_open() -> None:
    run = Run(
        id=uuid.uuid4(),
        product_system_id=uuid.uuid4(),
        at_hash="0" * 64,
        config=MonteCarloConfig(),
        posted_at=datetime.now(UTC),
    )
    assert run.cancellation() == RunPatch(cancel_requested=True)
    finished = RunPatch(status="done").applied_to(run)
    with pytest.raises(Conflict, match="cannot be cancelled after it has finished"):
        finished.cancellation()


def test_compartments_are_tallied_in_name_order_and_an_unplaced_flow_is_not_counted() -> None:
    placed = [("water", "ocean"), ("air", None), ("air", "urban"), ("", None), ("air", "urban")]
    assert Compartment.tally(placed) == [
        Compartment(name="air", flow_count=3, sub_compartments=["urban"]),
        Compartment(name="water", flow_count=1, sub_compartments=["ocean"]),
    ]


def test_a_fraction_is_the_share_of_its_total_and_none_of_a_total_of_zero() -> None:
    assert fraction_of(1.0, 4.0) == 0.25
    assert fraction_of(-1.0, 4.0) == -0.25
    assert fraction_of(1.0, 0.0) == 0.0


def install_draft(
    source: SourceName = "uslci",
    version: str | None = None,
    accept_terms: bool = False,
) -> InstallDraft:
    return InstallDraft(
        source=source,
        actor=Actor(kind="person", name="carlos"),
        version=version,
        accept_terms=accept_terms,
    )


def posted(draft: InstallDraft) -> Install:
    return Install(id=uuid.UUID(int=7), draft=draft, posted_at=datetime.now(UTC))


def test_an_account_never_shows_its_password() -> None:
    account = Account(username="carlos", password="s3cret")
    assert account.username == "carlos"
    assert account.password.get_secret_value() == "s3cret"
    assert "s3cret" not in repr(account)
    assert "s3cret" not in account.model_dump_json()
    with pytest.raises(ValidationError):
        account.username = "someone"


def test_a_source_names_the_credential_it_needs() -> None:
    assert source_credential("ecoinvent") == "ecoinvent"
    assert source_credential("bafu") == "nexus"
    assert source_credential("openlca") is None
    assert source_credential("uslci") is None


def test_a_source_carries_its_versions_what_it_needs_and_whether_it_is_held() -> None:
    bafu = DatabaseSource(
        name="bafu",
        versions=["2026"],
        system_models=["cutoff"],
        credential="nexus",
        terms=True,
    )
    assert bafu.held is False and bafu.versions == ["2026"]
    held = DatabaseSource(
        name="uslci", versions=[], system_models=[], credential=None, terms=False, held=True
    )
    assert held.held is True and held.credential is None


def test_an_install_is_open_while_queued_or_running() -> None:
    made = posted(install_draft())
    assert made.status == "queued" and made.open is True
    assert InstallPatch(status="running").applied_to(made).open is True
    assert InstallPatch(status="terms").applied_to(made).open is False
    assert InstallPatch(status="done").applied_to(made).open is False
    assert InstallPatch(status="failed").applied_to(made).open is False
    assert InstallPatch(status="cancelled").applied_to(made).open is False


def test_a_finished_install_refuses_cancellation() -> None:
    made = posted(install_draft())
    assert made.cancellation() == InstallPatch(cancel_requested=True)
    finished = InstallPatch(status="done").applied_to(made)
    with pytest.raises(Conflict, match="cannot be cancelled after it has finished"):
        finished.cancellation()


def test_an_openlca_draft_needs_its_package_name_and_version() -> None:
    actor = Actor(kind="person")
    with pytest.raises(ValidationError, match="needs package, name, version and system_model"):
        InstallDraft(source="openlca", actor=actor)
    with pytest.raises(ValidationError, match="needs package, name, version and system_model"):
        InstallDraft(source="openlca", actor=actor, package="uploads/a.zip", name="a")
    with pytest.raises(ValidationError, match="it lacks system_model"):
        InstallDraft(
            source="openlca", actor=actor, package="uploads/a.zip", name="a", version="1.0"
        )
    whole = InstallDraft(
        source="openlca",
        actor=actor,
        package="uploads/a.zip",
        name="a",
        version="1.0",
        system_model="unit process",
    )
    assert whole.drop_unlinked is False and whole.replace is False


def test_an_ecoinvent_draft_needs_its_version() -> None:
    with pytest.raises(ValidationError, match="needs a version"):
        InstallDraft(source="ecoinvent", actor=Actor(kind="person"))
    with pytest.raises(ValidationError, match="and a system model"):
        InstallDraft(source="ecoinvent", actor=Actor(kind="person"), version="3.11")
    drafted = InstallDraft(
        source="ecoinvent", actor=Actor(kind="person"), version="3.11", system_model="cutoff"
    )
    assert drafted.version == "3.11"


def test_a_patch_changes_only_the_fields_it_names() -> None:
    made = posted(install_draft())
    running = InstallPatch(status="running", pid=7).applied_to(made)
    assert running.status == "running" and running.pid == 7
    assert running.posted_at == made.posted_at and running.draft == made.draft
    # a field named as none is replaced by none; a field left out is kept
    assert InstallPatch(pid=None).applied_to(running).pid is None
    assert running.status == "running" and made.status == "queued" and made.pid is None


def test_an_install_carries_its_progress_and_the_terms_it_stopped_at() -> None:
    made = posted(install_draft())
    assert made.progress is None and made.terms is None and made.summary is None
    stepped = InstallPatch(progress=InstallProgress(step="compile", count=3)).applied_to(made)
    assert stepped.progress == InstallProgress(step="compile", count=3)
    assert InstallProgress(step="compile").count is None
    terms = InstallTerms(licence="licence.txt", citation="cite the release")
    assert InstallPatch(terms=terms).applied_to(made).terms == terms


def test_a_run_and_an_install_are_open_exactly_while_queued_or_running() -> None:
    assert {s for s in get_args(RunStatus) if is_open(s)} == {"queued", "running"}
    assert {s for s in get_args(InstallStatus) if is_open(s)} == {"queued", "running"}


def test_a_patch_replaces_only_the_fields_it_names_a_none_included() -> None:
    run = Run(
        id=uuid.uuid4(),
        product_system_id=uuid.uuid4(),
        at_hash="0" * 64,
        config=MonteCarloConfig(),
        posted_at=datetime.now(UTC),
        pid=7,
    )
    out = patched(run, RunPatch(status="running", pid=None))
    assert out.status == "running" and out.pid is None and out.config == run.config


def test_a_flat_list_shows_what_reaches_the_cutoff_up_to_its_length_and_counts_the_rest() -> None:
    fractions = [0.75, 0.2, -0.03, 0.02, 0.004, -0.002]
    shown, cut = listed(fractions, top_n=2, cutoff=0.01)
    assert (shown, cut.cutoff, cut.below, cut.unlisted) == (2, 0.01, 2, 2)
    assert cut.share == pytest.approx(0.006)
    assert cut.unlisted_share == pytest.approx(0.05)
    shown, cut = listed(fractions, top_n=10, cutoff=0.01)
    assert (shown, cut.below, cut.unlisted, cut.unlisted_share) == (4, 2, 0, 0.0)
    shown, cut = listed(fractions, top_n=10, cutoff=0.0)
    assert (shown, cut.below, cut.share, cut.unlisted) == (6, 0, 0.0, 0)
