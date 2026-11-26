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
from ecosemantic.model.entities import Actor, Method, ProductSystem, method_by_id
from ecosemantic.model.refs import DemandItem, ElementaryFlowRef, ForegroundRef
from ecosemantic.ports.resolver import FlowInfo
from ecosemantic.ports.types import (
    ADAPTIVE_N_MIN,
    FLOW_TYPES,
    Account,
    Change,
    Compartment,
    DatabaseSource,
    ElementaryFlow,
    Factor,
    Histogram,
    Install,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    InstallStatus,
    InstallTerms,
    InventoryRow,
    LogEntry,
    MonteCarloCategory,
    MonteCarloConfig,
    MonteCarloResult,
    MonteCarloSummary,
    Page,
    Run,
    RunPatch,
    RunStatus,
    SourceName,
    Spot,
    SubCompartment,
    System,
    TreeNode,
    factor_page,
    flow_side,
    fraction_of,
    is_open,
    listed,
    page_holding,
    page_start,
    patched,
    side_of,
    source_credential,
)
from tests.conftest import drawn_counts
from tests.fixture_data import FIXTURE_DATABASE


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


def test_an_adaptive_run_refuses_n_min_below_6() -> None:
    with pytest.raises(ValidationError) as caught:
        MonteCarloConfig(n_min=5, n_max=40)
    assert "an adaptive run takes n_min of at least 6" in str(caught.value)
    assert MonteCarloConfig(n=3, n_min=1).n_min == 1
    assert ADAPTIVE_N_MIN == 6


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


def test_a_page_points_back_only_past_its_first_row() -> None:
    assert Page.at_offset([1], False, 4, 2).previous_cursor == "2"
    assert Page.at_offset([1], False, 1, 2).previous_cursor == "0"
    assert Page.at_offset([1], False, 0, 2).previous_cursor is None


def test_page_holding_is_the_offset_of_the_items_page() -> None:
    assert page_holding(5, 2) == 4
    assert page_holding(0, 25) == 0
    assert page_holding(None, 25) == 0


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


def test_an_economic_flow_is_an_output() -> None:
    assert flow_side("economic", "unspecified") == "output"
    assert flow_side("economic", None) == "output"
    assert flow_side("economic", "non-FEDEFL") == "output"
    assert flow_side("economic", "primary production factor") == "input"


def test_side_of_answers_none_for_a_pair_the_table_does_not_name() -> None:
    assert side_of("inventory indicator", "unspecified") is None
    assert side_of("inventory indicator", None) is None
    assert side_of("economic", "unspecified") == "output"
    assert side_of("natural resource", "in water") == "input"


def test_flow_side_refuses_a_pair_the_table_does_not_name() -> None:
    with pytest.raises(NotSupported):
        flow_side("inventory indicator", None)
    with pytest.raises(NotSupported):
        flow_side("inventory indicator", "unspecified")


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
    fields = {
        "name": "x",
        "compartment": "inventory indicator",
        "sub_compartment": None,
        "unit": "kg",
    }
    with pytest.raises(NotSupported):
        ElementaryFlow(ref=ref, flow_type="inventory indicator", **fields)
    with pytest.raises(NotSupported):
        InventoryRow(flow=ref, flow_type="inventory indicator", amount=1.0, **fields)
    with pytest.raises(NotSupported):
        FlowInfo(flow_type="inventory indicator", **fields)


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


def test_compartments_are_tallied_in_name_order() -> None:
    placed = [("water", "ocean"), ("air", None), ("air", "urban"), ("air", "urban")]
    assert Compartment.tally(placed) == [
        Compartment(
            name="air",
            flow_count=3,
            sub_compartments=[SubCompartment(name="urban", flow_count=2)],
        ),
        Compartment(
            name="water",
            flow_count=1,
            sub_compartments=[SubCompartment(name="ocean", flow_count=1)],
        ),
    ]


def _factor(name: str, compartment: str, sub_compartment: str | None) -> Factor:
    return Factor(
        flow=ElementaryFlowRef(database="bio", id="0"),
        name=name,
        compartment=compartment,
        sub_compartment=sub_compartment,
        unit="kilogram",
        factor=1.0,
    )


def test_factors_are_ordered_by_name_compartment_and_sub_compartment() -> None:
    factors = [
        _factor("Benzene", "air", "urban air close to ground"),
        _factor("Benzene", "air", None),
        _factor("Ammonia", "water", None),
        _factor("Benzene", "air", "indoor"),
    ]
    first = factor_page(factors, None, 2, None)
    assert [(f.name, f.compartment, f.sub_compartment) for f in first.items] == [
        ("Ammonia", "water", None),
        ("Benzene", "air", None),
    ]
    assert first.has_more and first.next_cursor == "2"
    assert first.total == 4
    rest = factor_page(factors, None, 2, first.next_cursor)
    assert [f.sub_compartment for f in rest.items] == ["indoor", "urban air close to ground"]
    assert not rest.has_more
    # every word must sit in one of the factor's own fields, case-folded
    indoor = factor_page(factors, "AIR indoor", 10, None)
    assert [f.sub_compartment for f in indoor.items] == ["indoor"]
    assert indoor.total == 1


def test_a_share_of_a_total_of_0_is_none() -> None:
    assert fraction_of(1.0, 4.0) == 0.25
    assert fraction_of(-1.0, 4.0) == -0.25
    assert fraction_of(1.0, 0.0) is None
    assert fraction_of(0.0, 0.0) is None


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


def test_a_flat_list_shows_what_reaches_the_cutoff_up_to_its_length_and_signs_the_rest() -> None:
    scores = [0.75, 0.2, -0.03, 0.02, 0.004, -0.002]
    total = sum(scores)
    shown, cut = listed(scores, total, top_n=2, cutoff=0.01)
    assert (shown, cut.cutoff, cut.below, cut.unlisted) == (2, 0.01, 2, 2)
    assert cut.share == pytest.approx(0.006 / total)
    assert cut.unlisted_share == pytest.approx(0.05 / total)
    assert (cut.below_score, cut.unlisted_score) == (pytest.approx(0.002), pytest.approx(-0.01))
    assert sum(scores[:shown]) + cut.below_score + cut.unlisted_score == pytest.approx(total)
    shown, cut = listed(scores, total, top_n=10, cutoff=0.01)
    assert (shown, cut.below, cut.unlisted, cut.unlisted_share) == (4, 2, 0, 0.0)
    assert (cut.below_score, cut.unlisted_score) == (pytest.approx(0.002), 0)
    assert sum(scores[:shown]) + cut.below_score + cut.unlisted_score == pytest.approx(total)
    shown, cut = listed(scores, total, top_n=10, cutoff=0.0)
    assert (shown, cut.below, cut.share, cut.unlisted) == (6, 0, 0.0, 0)
    assert (cut.below_score, cut.unlisted_score) == (0, 0)


def test_a_total_of_0_lists_its_largest_parts_without_shares() -> None:
    scores = [28.0, -16.0, -12.0]
    shown, cut = listed(scores, 0.0, top_n=2, cutoff=0.01)
    assert (shown, cut.below, cut.unlisted) == (2, 0, 1)
    assert (cut.share, cut.unlisted_share) == (None, None)
    assert (cut.below_score, cut.unlisted_score) == (0, -12.0)
    shown, cut = listed(scores, 0.0, top_n=10, cutoff=0.01)
    assert (shown, cut.below, cut.unlisted) == (3, 0, 0)
    assert (cut.share, cut.unlisted_share) == (None, None)
    assert (cut.below_score, cut.unlisted_score) == (0, 0)


def _sampled(samples: list[float] | None) -> MonteCarloResult:
    method = Method.of(("fixture", "gwp", "climate change", "climate change"), "kg CO2-Eq")
    summary = MonteCarloSummary(
        n=3, mean=2.0, median=2.0, median_ci95=None, percentiles=(1.0, 3.0), rel_se=None
    )
    return MonteCarloResult(
        database=FIXTURE_DATABASE,
        n=3,
        stopped="fixed",
        gating_method=None,
        constant=[],
        indistinguishable_from_zero=[],
        scope="full",
        drawn=drawn_counts(),
        credit_loops=[],
        dropped_draws=[],
        dropped_loops=[],
        dropped_background=[],
        categories=[MonteCarloCategory(method_id=method.id, summary=summary, samples=samples)],
    )


def test_without_samples_answers_each_category_s_histogram_and_no_samples() -> None:
    sampled = _sampled([1.0, 2.0, 3.0])
    bare = sampled.without_samples()
    assert [category.samples for category in bare.categories] == [None]
    assert [category.summary for category in bare.categories] == [
        category.summary for category in sampled.categories
    ]
    assert [category.histogram for category in bare.categories] == [Histogram.of([1.0, 2.0, 3.0])]
    assert bare.model_dump(exclude={"categories"}) == sampled.model_dump(exclude={"categories"})
    assert sampled.categories[0].samples == [1.0, 2.0, 3.0]
    assert sampled.categories[0].histogram is None


def test_histogram_of_counts_twenty_bins_summing_to_the_number_of_draws() -> None:
    histogram = Histogram.of([float(draw) for draw in range(100)])
    assert len(histogram.counts) == 20
    assert sum(histogram.counts) == 100


def test_histogram_of_puts_the_smallest_draw_first_and_the_largest_last() -> None:
    histogram = Histogram.of([0.0, 0.9, 5.0, 19.9])
    assert (histogram.low, histogram.high) == (0.0, 19.9)
    assert histogram.counts[0] == 2
    assert histogram.counts[-1] == 1
    assert sum(histogram.counts) == 4


def test_histogram_of_counts_equal_draws_in_the_first_bin_with_low_equal_to_high() -> None:
    histogram = Histogram.of([5.0, 5.0, 5.0])
    assert (histogram.low, histogram.high) == (5.0, 5.0)
    assert len(histogram.counts) == 20
    assert histogram.counts == [3] + [0] * 19


def test_histogram_of_refuses_no_draws() -> None:
    with pytest.raises(Invalid) as caught:
        Histogram.of([])
    assert "draws" in str(caught.value)


def test_sampled_answers_the_draws_and_refuses_a_category_that_carries_none() -> None:
    sampled = _sampled([1.0, 2.0, 3.0])
    assert sampled.categories[0].sampled() == [1.0, 2.0, 3.0]
    with pytest.raises(Invalid) as caught:
        sampled.without_samples().categories[0].sampled()
    assert str(caught.value) == (
        "this Monte Carlo answer carries no samples; ask for them with samples"
    )


def test_a_method_is_the_one_its_id_names_and_an_id_none_carries_is_invalid() -> None:
    water = Method.of(("fixture", "water", "water scarcity", "water scarcity"), "m3")
    gwp = Method.of(("fixture", "gwp", "climate change", "climate change"), "kg CO2-Eq")
    assert method_by_id([water, gwp], gwp.id) == gwp
    with pytest.raises(Invalid) as caught:
        method_by_id([water, gwp], "m_ffffffffff")
    assert "m_ffffffffff" in str(caught.value)


def test_a_spot_refuses_a_number_that_is_not_finite() -> None:
    for x, y in ((float("inf"), 0.0), (0.0, float("nan"))):
        with pytest.raises(ValidationError):
            Spot(x=x, y=y)
