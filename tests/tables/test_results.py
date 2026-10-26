from __future__ import annotations

import csv
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ecosemantic.compute.results import ContributionResult, ImpactResult, VariantScores
from ecosemantic.model.entities import Method, method_id
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.types import (
    FlowHotspot,
    Hotspot,
    InventoryRow,
    LinkedLoop,
    MonteCarloCategory,
    MonteCarloResult,
    MonteCarloSummary,
    Page,
    Score,
    TreeNode,
)
from ecosemantic.tables.results import (
    ResultKey,
    method_label,
    run_name,
    write_contribution,
    write_impact,
    write_inventory,
)
from tests.fixture_data import FIXTURE_DATABASE

AT = datetime(2026, 9, 17, 14, 32, 5, tzinfo=UTC)
SPEC = "IPCC · GWP100"
GWP = Method(
    id=method_id(SPEC),
    tuple=("IPCC", "GWP100"),
    spec=SPEC,
    unit="kg CO2-Eq",
    impact_method="IPCC",
    impact_category="climate change",
    indicator="GWP100",
)


def key() -> ResultKey:
    return ResultKey(
        product_system_id=uuid.UUID(int=1),
        hash="9c1d" + "0" * 60,
        method=SPEC,
        demand=[],
        variants=["lean"],
    )


def test_the_run_directory_names_the_instant_and_what_it_scored() -> None:
    assert run_name(AT, "IPCC · GWP100") == "20260917T143205Z-ipcc-gwp100"
    assert run_name(AT, "inventory") == "20260917T143205Z-inventory"


def test_the_scores_table_carries_the_base_and_each_variant(tmp_path: Path) -> None:
    result = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="Battery pack",
        scores=[Score(value=4.21, unit="kg CO2-Eq", method=GWP)],
        credit_loops=[],
        variants=[
            VariantScores(
                name="lean",
                scores=[Score(value=3.02, unit="kg CO2-Eq", method=GWP)],
                deltas=[-1.19],
                credit_loops=[],
            )
        ],
    )
    folder = write_impact(tmp_path, key(), result, AT)
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["database"] == FIXTURE_DATABASE.model_dump(mode="json")
    rows = list(csv.DictReader((folder / "scores.csv").open()))
    assert rows[0]["variant"] == "" and rows[0]["score"] == "4.21" and rows[0]["delta"] == ""
    assert rows[0]["method_id"] == method_id(SPEC)
    assert rows[1]["variant"] == "lean" and rows[1]["delta"] == "-1.19"
    assert rows[0]["impact_category"] == "climate change"


def test_the_run_schema_carries_the_key_it_was_computed_on(tmp_path: Path) -> None:
    result = ImpactResult(
        database=FIXTURE_DATABASE, product_system="Battery pack", scores=[], credit_loops=[]
    )
    folder = write_impact(tmp_path, key(), result, AT)
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["format"] == 1
    assert schema["key"]["hash"] == key().hash
    assert schema["key"]["product_system_id"] == str(uuid.UUID(int=1))
    assert schema["key"]["variants"] == ["lean"]


def test_a_contribution_over_processes_writes_its_own_columns(tmp_path: Path) -> None:
    result = ContributionResult(
        database=FIXTURE_DATABASE,
        by="process",
        total=Score(value=4.21, unit="kg CO2-Eq", method=GWP),
        credit_loops=[],
        processes=[
            Hotspot(
                rank=1,
                ref=BackgroundRef(database="ei", id="transport-rer"),
                name="transport",
                location="RER",
                reference_product="tkm",
                score=2.0,
                fraction=0.48,
            )
        ],
    )
    folder = write_contribution(tmp_path, key(), result, AT)
    rows = list(csv.DictReader((folder / "contributions.csv").open()))
    assert rows[0]["rank"] == "1" and rows[0]["name"] == "transport"
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["by"] == "process"


def test_a_monte_carlo_block_writes_the_summary_and_the_samples(tmp_path: Path) -> None:
    result = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="Battery pack",
        scores=[Score(value=4.21, unit="kg CO2-Eq", method=GWP)],
        credit_loops=[],
        uncertainty=MonteCarloResult(
            database=FIXTURE_DATABASE,
            n=6,
            stopped="target",
            gating_method=GWP,
            scope="full",
            normals_at_amount=4,
            credit_loops=[],
            dropped_draws=[],
            dropped_loops=[],
            dropped_background=[],
            categories=[
                MonteCarloCategory(
                    method=GWP,
                    summary=MonteCarloSummary(
                        n=6,
                        mean=4.2,
                        median=4.2,
                        median_ci95=(4.0, 4.4),
                        percentiles=(4.01, 4.39),
                        rel_se=0.02,
                    ),
                    samples=[4.0, 4.2, 4.4, 4.1, 4.3, 4.2],
                )
            ],
        ),
    )
    folder = write_impact(tmp_path, key(), result, AT)
    summary = list(csv.DictReader((folder / "uncertainty.csv").open()))
    assert summary[0]["n"] == "6" and summary[0]["stopped"] == "target"
    assert summary[0]["normals_at_amount"] == "4"
    assert summary[0]["median"] == "4.2" and summary[0]["mean"] == "4.2"
    assert summary[0]["median_ci95_low"] == "4.0" and summary[0]["median_ci95_high"] == "4.4"
    assert summary[0]["rel_se"] == "0.02"
    assert summary[0]["p2_5"] == "4.01" and summary[0]["p97_5"] == "4.39"
    samples = list(csv.DictReader((folder / "samples.csv").open()))
    assert [row["iteration"] for row in samples] == ["0", "1", "2", "3", "4", "5"]
    assert [row["value"] for row in samples] == ["4.0", "4.2", "4.4", "4.1", "4.3", "4.2"]


def test_a_contribution_over_flows_writes_its_own_columns(tmp_path: Path) -> None:
    result = ContributionResult(
        database=FIXTURE_DATABASE,
        by="flow",
        total=Score(value=4.21, unit="kg CO2-Eq", method=GWP),
        credit_loops=[],
        flows=[
            FlowHotspot(
                rank=1,
                flow=ElementaryFlowRef(database="bio", id="co2"),
                name="carbon dioxide",
                compartment="air",
                amount=3.0,
                unit="kg",
                score=3.0,
                fraction=0.71,
            )
        ],
    )
    folder = write_contribution(tmp_path, key(), result, AT)
    rows = list(csv.DictReader((folder / "contributions.csv").open()))
    assert rows[0]["compartment"] == "air" and rows[0]["amount"] == "3.0"
    assert yaml.safe_load((folder / "schema.yaml").read_text())["by"] == "flow"


def test_a_contribution_over_paths_flattens_the_tree_in_walk_order(tmp_path: Path) -> None:
    leaf = TreeNode(name="transport", location="RER", score=1.0, fraction=0.24, level=1)
    root = TreeNode(
        name="battery", location="CH", score=4.21, fraction=1.0, level=0, children=[leaf]
    )
    result = ContributionResult(
        database=FIXTURE_DATABASE,
        by="path",
        total=Score(value=4.21, unit="kg CO2-Eq", method=GWP),
        credit_loops=[],
        root=root,
        truncated=False,
    )
    folder = write_contribution(tmp_path, key(), result, AT)
    rows = list(csv.DictReader((folder / "contributions.csv").open()))
    assert [row["level"] for row in rows] == ["0", "1"]
    assert [row["name"] for row in rows] == ["battery", "transport"]
    # a node with no reference leaves the cell blank
    assert rows[0]["ref"] == ""
    assert yaml.safe_load((folder / "schema.yaml").read_text())["truncated"] is False


def test_a_result_is_labelled_by_its_method_id_then_its_impact_method_then_nothing() -> None:
    assert method_label("m_0123456789", None) == "m_0123456789"
    assert method_label(None, "IPCC 2021") == "IPCC 2021"
    assert method_label("m_0123456789", "IPCC 2021") == "m_0123456789"
    assert method_label(None, None) == ""


def test_each_run_schema_names_the_loops_holding_a_credit(tmp_path: Path) -> None:
    loop = [["frame", "widget"]]
    linked = [LinkedLoop(product_system_id=uuid.uuid4(), at_hash="a" * 64, codes=["part", "rim"])]
    dumped = [inside.model_dump(mode="json") for inside in linked]
    total = Score(value=4.21, unit="kg CO2-Eq", method=GWP)
    impact = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="Widget",
        scores=[total],
        credit_loops=loop,
        linked_credit_loops=linked,
        variants=[VariantScores(name="lean", scores=[total], deltas=[0.0], credit_loops=[])],
    )
    schema = yaml.safe_load((write_impact(tmp_path, key(), impact, AT) / "schema.yaml").read_text())
    assert schema["credit_loops"] == loop and schema["linked_credit_loops"] == dumped
    assert schema["variant_credit_loops"] == {"lean": []}
    decomposed = ContributionResult(
        database=FIXTURE_DATABASE,
        by="process",
        total=total,
        processes=[],
        credit_loops=loop,
        linked_credit_loops=linked,
    )
    folder = write_contribution(tmp_path / "c", key(), decomposed, AT)
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["credit_loops"] == loop and schema["linked_credit_loops"] == dumped
    rows = Page[InventoryRow](items=[], has_more=False)
    folder = write_inventory(tmp_path / "i", key(), FIXTURE_DATABASE, rows, loop, linked, [], AT)
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["credit_loops"] == loop and schema["linked_credit_loops"] == dumped
    assert schema["database"] == FIXTURE_DATABASE.model_dump(mode="json")


def test_each_run_schema_names_the_exchanges_running_a_treatment_backwards(
    tmp_path: Path,
) -> None:
    named = ["frame · steel at 2.4", "widget · steel at 0.5"]
    doubled = ["frame · steel at 2.4", "widget · steel at 1"]
    total = Score(value=4.21, unit="kg CO2-Eq", method=GWP)
    variant = VariantScores(
        name="lean", scores=[total], deltas=[0.0], credit_loops=[], treatments_run_backwards=doubled
    )
    impact = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="Widget",
        scores=[total],
        credit_loops=[],
        treatments_run_backwards=named,
        variants=[variant],
    )
    schema = yaml.safe_load((write_impact(tmp_path, key(), impact, AT) / "schema.yaml").read_text())
    assert schema["treatments_run_backwards"] == named
    assert schema["variant_treatments_run_backwards"] == {"lean": doubled}
    decomposed = ContributionResult(
        database=FIXTURE_DATABASE,
        by="process",
        total=total,
        processes=[],
        credit_loops=[],
        treatments_run_backwards=named,
    )
    folder = write_contribution(tmp_path / "c", key(), decomposed, AT)
    assert yaml.safe_load((folder / "schema.yaml").read_text())["treatments_run_backwards"] == named
    rows = Page[InventoryRow](items=[], has_more=False)
    folder = write_inventory(tmp_path / "i", key(), FIXTURE_DATABASE, rows, [], [], named, AT)
    assert yaml.safe_load((folder / "schema.yaml").read_text())["treatments_run_backwards"] == named


def test_the_uncertainty_tables_count_the_dropped_draws_and_number_samples_by_draw(
    tmp_path: Path,
) -> None:
    # three draws, the second dropped
    result = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="Widget",
        scores=[Score(value=4.21, unit="kg CO2-Eq", method=GWP)],
        credit_loops=[],
        uncertainty=MonteCarloResult(
            database=FIXTURE_DATABASE,
            n=2,
            stopped="ceiling",
            gating_method=GWP,
            scope="full",
            normals_at_amount=0,
            credit_loops=[],
            dropped_draws=[1],
            dropped_loops=[["widget"]],
            dropped_background=["pellet production [GLO]"],
            categories=[
                MonteCarloCategory(
                    method=GWP,
                    summary=MonteCarloSummary(
                        n=2,
                        mean=4.2,
                        median=4.2,
                        median_ci95=None,
                        percentiles=(4.01, 4.39),
                        rel_se=None,
                    ),
                    samples=[4.0, 4.4],
                )
            ],
        ),
    )
    folder = write_impact(tmp_path, key(), result, AT)
    summary = list(csv.DictReader((folder / "uncertainty.csv").open()))
    assert summary[0]["n"] == "2" and summary[0]["dropped"] == "1"
    # below six samples the median has no interval and no relative error, and the cells are blank
    assert summary[0]["median_ci95_low"] == "" and summary[0]["median_ci95_high"] == ""
    assert summary[0]["rel_se"] == ""
    samples = list(csv.DictReader((folder / "samples.csv").open()))
    assert [row["iteration"] for row in samples] == ["0", "2"]
    schema = yaml.safe_load((folder / "schema.yaml").read_text())
    assert schema["dropped_loops"] == [["widget"]]
    assert schema["dropped_background"] == ["pellet production [GLO]"]
