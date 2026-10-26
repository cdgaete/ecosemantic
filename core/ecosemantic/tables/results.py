"""A calculation as a run folder: the tables it answers and the key it was computed on."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ecosemantic.compute.results import ContributionResult, ImpactResult
from ecosemantic.model.entities import DemandItem
from ecosemantic.model.refs import Database, slug
from ecosemantic.ports.types import InventoryRow, LinkedLoop, MonteCarloResult, Page, TreeNode
from ecosemantic.tables.folder import FORMAT, SCHEMA_FILE, number, write_csv

RESULTS_DIR = "results"
SCORES = "scores.csv"
UNCERTAINTY = "uncertainty.csv"
SAMPLES = "samples.csv"
CONTRIBUTIONS = "contributions.csv"
INVENTORY = "inventory.csv"

SCORE_COLUMNS = [
    "variant",
    "method_id",
    "impact_method",
    "impact_category",
    "indicator",
    "score",
    "unit",
    "delta",
]


class ResultKey(BaseModel):
    """What one result was computed on; nothing answers for a different key."""

    product_system_id: uuid.UUID
    hash: str
    method: str = ""
    demand: list[DemandItem] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)


def method_label(method_id: str | None, impact_method: str | None) -> str:
    """What a result names the method it was scored by: its id, or else its impact method, or
    blank where the calculation characterises nothing."""
    return method_id or impact_method or ""


def run_name(at: datetime, label: str) -> str:
    """The run directory: the UTC instant it was computed at and what the run scored.

    An impact or a contribution labels itself with its method. An inventory characterises
    nothing, so it labels itself `inventory` rather than carrying an empty method.
    """
    return f"{at.strftime('%Y%m%dT%H%M%SZ')}-{slug(label, '-')}"


def _open(root: Path, key: ResultKey, at: datetime, label: str, extra: dict[str, object]) -> Path:
    folder = root / RESULTS_DIR / run_name(at, label)
    folder.mkdir(parents=True, exist_ok=True)
    schema: dict[str, object] = {
        "format": FORMAT,
        "key": {
            "product_system_id": str(key.product_system_id),
            "hash": key.hash,
            "method": key.method,
            "demand": [item.model_dump(mode="json") for item in key.demand],
            "variants": list(key.variants),
        },
        "computed_at": at.isoformat(),
    }
    schema.update(extra)
    (folder / SCHEMA_FILE).write_text(
        yaml.safe_dump(schema, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return folder


def write_impact(root: Path, key: ResultKey, result: ImpactResult, at: datetime) -> Path:
    """The scores, and the uncertainty and its samples when a Monte Carlo block ran; the schema
    names the loops holding a credit in the base, inside the systems it links and in each
    variant, the exchanges running a treatment backwards in the base and in each variant, and
    the loops and background processes whose draws the Monte Carlo dropped."""
    named: dict[str, object] = {
        "product_system": result.product_system,
        "database": result.database.model_dump(mode="json"),
        "credit_loops": result.credit_loops,
        "linked_credit_loops": [
            loop.model_dump(mode="json") for loop in result.linked_credit_loops
        ],
        "variant_credit_loops": {v.name: v.credit_loops for v in result.variants},
        "treatments_run_backwards": result.treatments_run_backwards,
        "variant_treatments_run_backwards": {
            v.name: v.treatments_run_backwards for v in result.variants
        },
    }
    if result.uncertainty is not None:
        named["dropped_loops"] = result.uncertainty.dropped_loops
        named["dropped_linked_loops"] = [
            loop.model_dump(mode="json") for loop in result.uncertainty.dropped_linked_loops
        ]
        named["dropped_background"] = result.uncertainty.dropped_background
    folder = _open(root, key, at, key.method, named)
    rows = [
        {
            "variant": "",
            "method_id": score.method.id,
            "impact_method": score.method.impact_method,
            "impact_category": score.method.impact_category,
            "indicator": score.method.indicator,
            "score": number(score.value),
            "unit": score.unit,
            "delta": "",
        }
        for score in result.scores
    ]
    for variant in result.variants:
        for score, delta in zip(variant.scores, variant.deltas, strict=True):
            rows.append(
                {
                    "variant": variant.name,
                    "method_id": score.method.id,
                    "impact_method": score.method.impact_method,
                    "impact_category": score.method.impact_category,
                    "indicator": score.method.indicator,
                    "score": number(score.value),
                    "unit": score.unit,
                    "delta": number(delta),
                }
            )
    write_csv(folder / SCORES, SCORE_COLUMNS, rows)
    if result.uncertainty is not None:
        _write_uncertainty(folder, result.uncertainty)
    return folder


def _write_uncertainty(folder: Path, uncertainty: MonteCarloResult) -> None:
    write_csv(
        folder / UNCERTAINTY,
        [
            "method_id",
            "n",
            "stopped",
            "scope",
            "normals_at_amount",
            "dropped",
            "median",
            "median_ci95_low",
            "median_ci95_high",
            "rel_se",
            "p2_5",
            "p97_5",
            "mean",
        ],
        [
            {
                "method_id": category.method.id,
                "n": str(category.summary.n),
                "stopped": uncertainty.stopped,
                "scope": uncertainty.scope,
                "normals_at_amount": str(uncertainty.normals_at_amount),
                "dropped": str(len(uncertainty.dropped_draws)),
                "median": number(category.summary.median),
                "median_ci95_low": number(interval[0] if interval is not None else None),
                "median_ci95_high": number(interval[1] if interval is not None else None),
                "rel_se": number(category.summary.rel_se),
                "p2_5": number(category.summary.percentiles[0]),
                "p97_5": number(category.summary.percentiles[1]),
                "mean": number(category.summary.mean),
            }
            for category in uncertainty.categories
            for interval in [category.summary.median_ci95]
        ],
    )
    write_csv(
        folder / SAMPLES,
        ["method_id", "iteration", "value"],
        [
            {"method_id": category.method.id, "iteration": str(draw), "value": number(value)}
            for category in uncertainty.categories
            for draw, value in zip(uncertainty.draws(), category.samples, strict=True)
        ],
    )


def _walk(node: TreeNode) -> list[TreeNode]:
    return [node, *[descendant for child in node.children for descendant in _walk(child)]]


def write_contribution(
    root: Path, key: ResultKey, result: ContributionResult, at: datetime
) -> Path:
    """One decomposition as a table; the schema names which column set it carries, the loops
    holding a credit, in the system and inside the systems it links, and the exchanges running a
    treatment backwards."""
    folder = _open(
        root,
        key,
        at,
        key.method,
        {
            "database": result.database.model_dump(mode="json"),
            "by": result.by,
            "truncated": result.truncated,
            "credit_loops": result.credit_loops,
            "linked_credit_loops": [
                loop.model_dump(mode="json") for loop in result.linked_credit_loops
            ],
            "treatments_run_backwards": result.treatments_run_backwards,
        },
    )
    if result.processes is not None:
        write_csv(
            folder / CONTRIBUTIONS,
            ["rank", "ref", "name", "location", "reference_product", "score", "fraction"],
            [
                {
                    "rank": str(item.rank),
                    "ref": item.ref.model_dump_json(),
                    "name": item.name,
                    "location": item.location or "",
                    "reference_product": item.reference_product,
                    "score": number(item.score),
                    "fraction": number(item.fraction),
                }
                for item in result.processes
            ],
        )
    elif result.flows is not None:
        write_csv(
            folder / CONTRIBUTIONS,
            ["rank", "flow", "name", "compartment", "amount", "unit", "score", "fraction"],
            [
                {
                    "rank": str(item.rank),
                    "flow": item.flow.model_dump_json(),
                    "name": item.name,
                    "compartment": item.compartment,
                    "amount": number(item.amount),
                    "unit": item.unit,
                    "score": number(item.score),
                    "fraction": number(item.fraction),
                }
                for item in result.flows
            ],
        )
    elif result.root is not None:
        write_csv(
            folder / CONTRIBUTIONS,
            ["level", "kind", "ref", "name", "location", "score", "fraction"],
            [
                {
                    "level": str(node.level),
                    "kind": node.kind,
                    "ref": "" if node.ref is None else node.ref.model_dump_json(),
                    "name": node.name,
                    "location": node.location or "",
                    "score": number(node.score),
                    "fraction": number(node.fraction),
                }
                for node in _walk(result.root)
            ],
        )
    return folder


def write_inventory(
    root: Path,
    key: ResultKey,
    database: Database,
    page: Page[InventoryRow],
    credit_loops: list[list[str]],
    linked_credit_loops: list[LinkedLoop],
    treatments_run_backwards: list[str],
    at: datetime,
) -> Path:
    """The inventory page the request asked for; its cursor is in the schema, so nothing is lost,
    beside the loops holding a credit, in the system and inside the systems it links, and the
    exchanges running a treatment backwards."""
    folder = _open(
        root,
        key,
        at,
        "inventory",
        {
            "database": database.model_dump(mode="json"),
            "has_more": page.has_more,
            "next_cursor": page.next_cursor,
            "credit_loops": credit_loops,
            "linked_credit_loops": [loop.model_dump(mode="json") for loop in linked_credit_loops],
            "treatments_run_backwards": treatments_run_backwards,
        },
    )
    write_csv(
        folder / INVENTORY,
        [
            "flow",
            "name",
            "compartment",
            "sub_compartment",
            "flow_type",
            "side",
            "unit",
            "amount",
            "source",
        ],
        [
            {
                "flow": row.flow.model_dump_json(),
                "name": row.name,
                "compartment": row.compartment,
                "sub_compartment": row.sub_compartment or "",
                "flow_type": row.flow_type,
                "side": row.side,
                "unit": row.unit,
                "amount": number(row.amount),
                "source": "" if row.source is None else row.source.model_dump_json(),
            }
            for row in page.items
        ],
    )
    return folder
