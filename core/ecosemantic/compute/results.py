"""The shapes a calculation answers with, where the tool layer and the writers both see them."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from ecosemantic.compute.montecarlo import PairedDelta
from ecosemantic.model.refs import Database
from ecosemantic.model.summary import Summary
from ecosemantic.ports.types import (
    Decomposition,
    FlowHotspot,
    Hotspot,
    LinkedLoop,
    MonteCarloResult,
    Score,
    TreeNode,
)


class VariantScores(BaseModel):
    """One variant's scores and its difference from the base, method by method, with the
    processes of each loop in the variant that holds a credit, whose delivery no check decides,
    and each exchange of the variant sending a positive amount to a treatment, which runs it
    backwards. `scores` are the point values and `deltas` each one less the base's, with or
    without a Monte Carlo block. A pair is the base's and the variant's draws at one position,
    over the first draws of each up to the shorter run, since each run's own stop rule ends it;
    `paired_deltas` hold each pair's difference with its interval and percentage, and
    `uncertainty` the variant's own samples at the base's seed, which can outnumber the
    pairs."""

    name: str
    scores: list[Score]
    deltas: list[float]
    credit_loops: list[list[str]]
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    treatments_run_backwards: list[str] = Field(default_factory=list)
    uncertainty: MonteCarloResult | None = None
    paired_deltas: list[PairedDelta] | None = None


class PinBehind(BaseModel):
    """A linked system whose pinned state no longer buys what that system now offers."""

    product_system_id: uuid.UUID
    name: str
    at_hash: str


class ImpactResult(BaseModel):
    """The characterised score of a product system over the database build `database` names,
    with variants and uncertainty, the processes of each loop holding a credit, whose delivery
    no check decides, the links the score was taken behind, and each exchange sending a
    positive amount to a treatment, which runs it backwards and scores its emissions as
    credits."""

    product_system: str
    database: Database
    scores: list[Score]
    credit_loops: list[list[str]]
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    links_behind: list[PinBehind] = Field(default_factory=list)
    treatments_run_backwards: list[str] = Field(default_factory=list)
    variants: list[VariantScores] = Field(default_factory=list)
    uncertainty: MonteCarloResult | None = None

    def summarise(self) -> Summary:
        """The base scores, one per method."""
        return Summary(scores=[score.summary_score() for score in self.scores])


class ContributionResult(BaseModel):
    """One decomposition of a total over the database build `database` names: flat over
    emitters, nested over paths, or flat over flows, with the processes of each loop holding a
    credit, whose delivery no check decides, and each exchange sending a positive amount to a
    treatment, which runs it backwards."""

    database: Database
    by: Decomposition
    total: Score
    credit_loops: list[list[str]]
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    treatments_run_backwards: list[str] = Field(default_factory=list)
    processes: list[Hotspot] | None = None
    root: TreeNode | None = None
    truncated: bool | None = None
    flows: list[FlowHotspot] | None = None

    def summarise(self) -> Summary:
        """The total the decomposition divides."""
        return Summary(scores=[self.total.summary_score()])

    @model_validator(mode="after")
    def _carried(self) -> ContributionResult:
        """A decomposition carries the rows its axis names and no others, so a writer that
        finds none has nothing to leave out."""
        carried = sorted(name for name in set(_ROWS.values()) if getattr(self, name) is not None)
        if carried != [_ROWS[self.by]]:
            raise ValueError(f"by={self.by!r} carries {_ROWS[self.by]}, not {carried}")
        return self


_ROWS: dict[Decomposition, str] = {"process": "processes", "path": "root", "flow": "flows"}
