"""The split of a score by life-cycle stage: each stage's processes, their own parts and inputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, ForegroundRef, LinkedProcessRef
from ecosemantic.model.stages import stage_of, stage_order
from ecosemantic.ports.types import OwnPart, OwnParts, fraction_of

StageInputKind = Literal["process", "remainder"]


class StageInput(BaseModel):
    """One input of a foreground process and its part of the score, or the one part standing for
    the inputs a cut-off folds away, which names no reference and no location."""

    kind: StageInputKind
    ref: BackgroundRef | LinkedProcessRef | None
    name: str
    location: str | None
    score: float
    fraction: float | None


class StageProcess(BaseModel):
    """One of the product system's own processes under its stage: its own part of the score, its
    direct emissions and its inputs, largest magnitude first."""

    ref: ForegroundRef
    name: str
    location: str | None
    score: float
    fraction: float | None
    direct: float
    inputs: list[StageInput]


class StagePart(BaseModel):
    """One life-cycle stage's part of the score and its processes; the part of a stage of None
    holds every process stating no stage."""

    stage: str | None
    score: float
    fraction: float | None
    processes: list[StageProcess]


def _inputs(part: OwnPart, total: float, floor: float) -> list[StageInput]:
    """The process's inputs largest magnitude first, the ones under the floor summed into one."""
    kept = [one for one in part.inputs if abs(one.score) >= floor]
    folded = [one for one in part.inputs if abs(one.score) < floor]
    inputs = [
        StageInput(
            kind="process",
            ref=one.ref,
            name=one.name,
            location=one.location,
            score=one.score,
            fraction=fraction_of(one.score, total),
        )
        for one in sorted(kept, key=lambda one: abs(one.score), reverse=True)
    ]
    if folded:
        remainder = sum(one.score for one in folded)
        inputs.append(
            StageInput(
                kind="remainder",
                ref=None,
                name="remainder",
                location=None,
                score=remainder,
                fraction=fraction_of(remainder, total),
            )
        )
    return inputs


def _process(process: Process, part: OwnPart, total: float, floor: float) -> StageProcess:
    """The process's own part under its stage."""
    return StageProcess(
        ref=part.ref,
        name=process.name,
        location=process.location,
        score=part.score,
        fraction=fraction_of(part.score, total),
        direct=part.direct,
        inputs=_inputs(part, total, floor),
    )


def by_stage(system: ProductSystem, parts: OwnParts, cutoff: float) -> list[StagePart]:
    """The stages of the system the own parts fall under, in the order a walk from its anchors
    meets them and the processes of no stage last, each process and each input largest magnitude
    first, and each input under `cutoff` of the total summed into one remainder that process's
    own score still holds."""
    total = parts.total.value
    floor = cutoff * abs(total)
    order: list[str | None] = [*stage_order(system), None]
    grouped: dict[str | None, list[StageProcess]] = {stage: [] for stage in order}
    for part in parts.parts:
        process = system.process(part.ref.code)
        grouped[stage_of(process)].append(_process(process, part, total, floor))
    answer: list[StagePart] = []
    for stage in order:
        processes = sorted(grouped[stage], key=lambda one: abs(one.score), reverse=True)
        if not processes:
            continue
        score = sum(process.score for process in processes)
        answer.append(
            StagePart(
                stage=stage,
                score=score,
                fraction=fraction_of(score, total),
                processes=processes,
            )
        )
    got = sum(part.score for part in answer)
    magnitudes = sum(abs(part.score) for part in parts.parts)
    if abs(got - total) > 1e-9 * magnitudes:
        raise Invalid(f"the split by stage sums to {got} and misses its total {total}")
    return answer
