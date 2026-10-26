"""A card's anatomy in the pixels the page draws it at, and where each of its rows is
anchored, so the server and the page describe one drawing."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import NamedTuple

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import ElementaryFlowRef, ForegroundRef, SystemRef
from ecosemantic.model.units import symbol
from ecosemantic.ports.types import Side
from ecosemantic.quantity import written

CARD_WIDTH = 300.0
COLUMN_GAP = 200.0
ROW_GAP = 40.0
COLUMN_TOP = 40.0
HEADER_HEIGHT = 40.0
SECTION_PADDING = 6.0
SECTION_LABEL = 18.0
ROW_HEIGHT = 22.0
FOLD_AFTER = 6
SECTION = 2 * SECTION_PADDING + SECTION_LABEL
LINKED_HEIGHT = HEADER_HEIGHT + 2 * SECTION_PADDING + ROW_HEIGHT
LINKED = "system:"


def linked_code(ref: SystemRef) -> str:
    """The key a linked system's card is drawn and held by."""
    return f"{LINKED}{ref.product_system_id}"


class Port(BaseModel):
    """Where one input row is anchored, as its offset from the top of its card."""

    exchange_id: uuid.UUID
    y: float


class Placement(BaseModel):
    """Where one card is drawn, its rows in drawn order with their anchors, the offset of its
    output anchor, and whether someone put it there."""

    code: str
    x: float
    y: float
    width: float
    height: float
    depth: int
    shown_inputs: int = 0
    row_height: float = ROW_HEIGHT
    held: bool = False
    inputs: list[Port] = []
    outputs: list[uuid.UUID] = []
    output: float
    activity: float | None = None
    scaled: dict[uuid.UUID, float] | None = None


def _is_input(exchange: Exchange, sides: Mapping[str, Side]) -> bool:
    if exchange.type == "product":
        return True
    return isinstance(exchange.input, ElementaryFlowRef) and sides[exchange.input.id] == "input"


def rows(process: Process, sides: Mapping[str, Side]) -> tuple[list[Exchange], list[Exchange]]:
    """A card's input rows and output rows in the order it draws them: the system's order, the
    production row first among the outputs, and rows at zero after the others."""
    inputs = [e for e in process.exchanges if _is_input(e, sides)]
    outputs = [e for e in process.exchanges if not _is_input(e, sides)]
    inputs.sort(key=lambda e: e.amount == 0)
    outputs.sort(key=lambda e: (e.type != "production", e.amount == 0))
    return inputs, outputs


def shown_inputs(process: Process, sides: Mapping[str, Side]) -> int:
    """How many input rows a card draws before its fold row."""
    return min(len(rows(process, sides)[0]), FOLD_AFTER)


def _folded(process: Process, sides: Mapping[str, Side]) -> int:
    return 1 if len(rows(process, sides)[0]) > FOLD_AFTER else 0


def card_size(process: Process, sides: Mapping[str, Side]) -> tuple[float, float]:
    """A card's width and height: the header, two sections, and a row per shown input, for the
    fold and per output."""
    outputs = len(rows(process, sides)[1])
    drawn = shown_inputs(process, sides) + _folded(process, sides) + outputs
    return CARD_WIDTH, HEADER_HEIGHT + 2 * SECTION + ROW_HEIGHT * drawn


def ports(process: Process, sides: Mapping[str, Side]) -> tuple[list[Port], float]:
    """Each input row's anchor, an input behind the fold on the fold row, and the production
    row's anchor, as offsets from the top of the card."""
    inputs, _ = rows(process, sides)
    shown = shown_inputs(process, sides)
    first = HEADER_HEIGHT + SECTION_PADDING + SECTION_LABEL + ROW_HEIGHT / 2
    found = [
        Port(exchange_id=e.id, y=first + ROW_HEIGHT * min(n, shown)) for n, e in enumerate(inputs)
    ]
    output = (
        HEADER_HEIGHT
        + SECTION
        + ROW_HEIGHT * (shown + _folded(process, sides))
        + SECTION_PADDING
        + SECTION_LABEL
        + ROW_HEIGHT / 2
    )
    return found, output


def linked_card() -> tuple[float, float, float]:
    """A linked system's card: its width, its height of a header and one row, and its output
    anchor at its middle."""
    return CARD_WIDTH, LINKED_HEIGHT, LINKED_HEIGHT / 2


class Link(BaseModel):
    """One arrow of a drawing: the card that provides, the card that consumes, and the input
    exchange it feeds."""

    provider: str
    consumer: str
    exchange_id: uuid.UUID


def links(system: ProductSystem) -> list[Link]:
    """Every arrow of a drawing, one per foreground or linked input, in the system's order."""
    codes = {p.code for p in system.processes}
    found: list[Link] = []
    for process in system.processes:
        for e in process.exchanges:
            if isinstance(e.input, ForegroundRef) and e.input.code in codes:
                found.append(Link(provider=e.input.code, consumer=process.code, exchange_id=e.id))
            elif isinstance(e.input, SystemRef):
                found.append(
                    Link(provider=linked_code(e.input), consumer=process.code, exchange_id=e.id)
                )
    return found


class LinkText(NamedTuple):
    """The texts one arrow can carry: per unit, scaled when the drawing is scaled, and the
    formula mark when the exchange has a formula."""

    per_unit: str
    scaled: str | None
    formula: str | None


def link_texts(
    system: ProductSystem, amounts: Mapping[str, Mapping[uuid.UUID, float]] | None
) -> dict[uuid.UUID, LinkText]:
    """Each exchange's per-unit text, its scaled text when the drawing is scaled, and its
    formula text when it has a formula, keyed by exchange id."""
    found: dict[uuid.UUID, LinkText] = {}
    for process in system.processes:
        if amounts is not None and process.code not in amounts:
            raise Invalid(f"no scaled amounts for card {process.code}")
        for e in process.exchanges:
            if amounts is None:
                scaled = None
            elif e.id in amounts[process.code]:
                scaled = written(amounts[process.code][e.id], e.unit)
            else:
                raise Invalid(f"card {process.code} has no scaled amount for exchange {e.id}")
            formula = None if e.formula is None else f"ƒ {symbol(e.unit)}"
            found[e.id] = LinkText(written(e.amount, e.unit), scaled, formula)
    return found
