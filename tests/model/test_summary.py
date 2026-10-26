from __future__ import annotations

from ecosemantic.compute.results import ContributionResult, ImpactResult
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.model.summary import SUMMARY_ITEMS, Summary, SummaryItem, SummaryScore, listed
from ecosemantic.ports.types import BackgroundProcess, ElementaryFlowHit, ProcessHit, Score
from tests.fixture_data import FIXTURE_DATABASE

GWP = Method.of(("fixture", "IPCC", "climate change", "GWP100"), "kg CO2-Eq")
GWP_SPEC = "fixture > IPCC > climate change > GWP100"


def hit(number: int) -> ProcessHit:
    return ProcessHit(
        ref=BackgroundRef(database="fixture", id=f"p{number}"),
        name=f"process {number}",
        reference_product="product",
        location="CL",
        unit="kg",
        relevance=1.0,
    )


def test_a_process_hit_is_an_item_that_opens_it() -> None:
    assert hit(1).summary_item() == SummaryItem(
        label="process 1", detail="CL", kind="background", database="fixture", ref="p1"
    )


def test_a_flow_hit_and_a_method_are_items() -> None:
    flow = ElementaryFlowHit(
        ref=ElementaryFlowRef(database="bio", id="f1"),
        name="Carbon dioxide",
        compartment="air",
        sub_compartment=None,
        unit="kg",
        flow_type="emission",
        cas_number=None,
    )
    assert flow.summary_item() == SummaryItem(
        label="Carbon dioxide", detail="air", kind="elementary_flow", database="bio", ref="f1"
    )
    assert GWP.summary_item() == SummaryItem(label=GWP_SPEC, detail="kg CO2-Eq", ref=GWP.id)


def test_a_listing_counts_all_and_keeps_the_first_items() -> None:
    summary = listed([hit(n) for n in range(7)], more=True)
    assert summary.count == 7 and summary.more
    assert [item.ref for item in summary.items] == [f"p{n}" for n in range(SUMMARY_ITEMS)]


def test_a_listing_of_things_that_are_not_items_is_a_count() -> None:
    assert listed(["a", "b"], more=False) == Summary(count=2)


def test_a_background_process_is_one_item() -> None:
    process = BackgroundProcess(
        ref=BackgroundRef(database="fixture", id="p1"),
        name="market for electricity",
        reference_product="electricity",
        location="CL",
        unit="kWh",
    )
    assert process.summarise() == Summary(
        count=1,
        items=[
            SummaryItem(
                label="market for electricity",
                detail="CL",
                kind="background",
                database="fixture",
                ref="p1",
            )
        ],
    )


def test_a_result_is_its_scores() -> None:
    score = Score(value=2.5, unit="kg CO2-Eq", method=GWP)
    expected = Summary(scores=[SummaryScore(method=GWP_SPEC, value=2.5, unit="kg CO2-Eq")])
    assert (
        ImpactResult(
            database=FIXTURE_DATABASE, product_system="bottle", scores=[score], credit_loops=[]
        ).summarise()
        == expected
    )
    assert (
        ContributionResult(
            database=FIXTURE_DATABASE, by="process", total=score, processes=[], credit_loops=[]
        ).summarise()
        == expected
    )
