"""The life-cycle stage a process states, and the order a product system's stages come in."""

from __future__ import annotations

from collections import deque

from pydantic import JsonValue

from ecosemantic.model.entities import Process, ProductSystem
from ecosemantic.model.refs import ForegroundRef
from ecosemantic.model.validation import anchors


def stage_of(process: Process) -> str | None:
    """The stage the process states, unchanged, or None when it states none. A stage that is
    not a string, or holds no character but space, is none."""
    stage: JsonValue = process.metadata["life_cycle_stage"]
    if isinstance(stage, str) and stage.strip():
        return stage
    return None


def stage_order(system: ProductSystem) -> list[str]:
    """Every named stage of the system, each once, in the order the walk from its anchors meets
    the processes carrying them, the processes the walk misses following in document order."""
    by_code = {process.code: process for process in system.processes}
    seen: set[str] = set()
    order: list[str] = []

    def record(process: Process) -> None:
        stage = stage_of(process)
        if stage is not None and stage not in order:
            order.append(stage)

    queue: deque[str] = deque(anchors(system))
    while queue:
        code = queue.popleft()
        process = by_code.get(code)
        if process is None or code in seen:
            continue
        seen.add(code)
        record(process)
        queue.extend(
            exchange.input.code
            for exchange in process.exchanges
            if isinstance(exchange.input, ForegroundRef)
        )
    for process in system.processes:
        if process.code not in seen:
            record(process)
    return order
