"""A card's anatomy in the pixels the page draws it at, and where each of its rows is
anchored, so the server and the page describe one drawing."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from typing import NamedTuple

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import ActorKind, Exchange, Process, ProductSystem
from ecosemantic.model.refs import ElementaryFlowRef, ForegroundRef, SystemRef
from ecosemantic.model.summary import SummaryItem
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


class CardGeometry(BaseModel):
    """A card's size in the pixels the page draws it at: its width, its header, the padding around
    a section and the label over its rows, and the height of one row."""

    width: float
    header_height: float
    section_padding: float
    section_label: float
    row_height: float


def card_geometry() -> CardGeometry:
    """The geometry every card is drawn at, which the arrangement carries once."""
    return CardGeometry(
        width=CARD_WIDTH,
        header_height=HEADER_HEIGHT,
        section_padding=SECTION_PADDING,
        section_label=SECTION_LABEL,
        row_height=ROW_HEIGHT,
    )


def linked_code(ref: SystemRef) -> str:
    """The key a linked system's card is drawn and held by."""
    return f"{LINKED}{ref.product_system_id}"


class Port(BaseModel):
    """Where one input row is anchored, as its offset from the top of its card."""

    exchange_id: uuid.UUID
    y: float


class Placement(BaseModel):
    """Where one card is drawn, the rows it shows of each side in drawn order with their anchors,
    the offset of its output anchor, whether someone put it there and who that was. `folded`
    counts the rows a fold hides, so a card whose rows are all shown still says what collapsing
    it would take away."""

    code: str
    x: float
    y: float
    width: float
    height: float
    depth: int
    shown_inputs: int
    shown_outputs: int
    folded_inputs: int = 0
    folded_outputs: int = 0
    held: bool = False
    placed_by: ActorKind | None = None
    inputs: list[Port] = []
    outputs: list[uuid.UUID] = []
    output: float
    activity: float | None = None
    scaled: dict[uuid.UUID, float] | None = None

    def summary_item(self) -> SummaryItem:
        """The card as one item a summary lists: the code it is drawn and named by."""
        return SummaryItem(label=self.code)


class Region(BaseModel):
    """A rectangle in the drawing's own coordinates, holding the cards of one stage."""

    x: float
    y: float
    width: float
    height: float


class StageRegions(BaseModel):
    """One stage's cards in the order the drawing places them, and the regions that hold them."""

    stage: str
    codes: list[str]
    regions: list[Region]


class SharedSupplier(BaseModel):
    """A card of no stage: how many processes it feeds and how many of the system's stages those
    processes span."""

    code: str
    processes: int
    stages: int


def _is_input(exchange: Exchange, sides: Mapping[str, Side]) -> bool:
    if exchange.type == "product":
        return True
    return isinstance(exchange.input, ElementaryFlowRef) and sides[exchange.input.id] == "input"


class Fold(NamedTuple):
    """The rows of one side of a card: how many it holds, how many it draws, and how many a fold
    hides when the card is collapsed."""

    total: int
    shown: int
    folded: int


def rows(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID] = (),
) -> tuple[list[Exchange], list[Exchange]]:
    """A card's input rows and output rows in the order it draws them: an input whose `arrows`
    holds its id first, the production row first among the outputs, and rows at zero after the
    others within each group."""
    inputs = [e for e in process.exchanges if _is_input(e, sides)]
    outputs = [e for e in process.exchanges if not _is_input(e, sides)]
    inputs.sort(key=lambda e: (e.id not in arrows, e.amount == 0))
    outputs.sort(key=lambda e: (e.type != "production", e.amount == 0))
    return inputs, outputs


def _fold(total: int, kept: int, expanded: bool) -> Fold:
    return Fold(total=total, shown=total if expanded else kept, folded=total - kept)


def _fold_row(found: Fold) -> int:
    """One row for the control that hides the rows a collapsed card does not show."""
    return 1 if found.shown < found.total else 0


def folds(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID] = (),
    *,
    expanded: bool = False,
) -> tuple[Fold, Fold]:
    """How many input rows and how many output rows a card draws, and how many a fold hides on
    each side: a card collapses to `FOLD_AFTER` rows a side, keeps every input that draws an
    arrow, and shows every row when `expanded`."""
    inputs, outputs = rows(process, sides, arrows)
    drawn = max(FOLD_AFTER, sum(1 for e in inputs if e.id in arrows))
    return (
        _fold(len(inputs), min(len(inputs), drawn), expanded),
        _fold(len(outputs), min(len(outputs), FOLD_AFTER), expanded),
    )


def shown_inputs(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID] = (),
    *,
    expanded: bool = False,
) -> int:
    """How many input rows a card draws before its fold row."""
    return folds(process, sides, arrows, expanded=expanded)[0].shown


def card_size(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID] = (),
    *,
    expanded: bool = False,
) -> tuple[float, float]:
    """A card's width and height: the header, two sections, a row per shown input and per shown
    output, and one more row each side whose fold hides rows."""
    inputs, outputs = folds(process, sides, arrows, expanded=expanded)
    drawn = inputs.shown + _fold_row(inputs) + outputs.shown + _fold_row(outputs)
    return CARD_WIDTH, HEADER_HEIGHT + 2 * SECTION + ROW_HEIGHT * drawn


def ports(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID] = (),
    *,
    expanded: bool = False,
) -> tuple[list[Port], float]:
    """Each input row's anchor, an input behind the fold on the fold row, and the production
    row's anchor, as offsets from the top of the card."""
    inputs, _ = rows(process, sides, arrows)
    found_fold = folds(process, sides, arrows, expanded=expanded)[0]
    first = HEADER_HEIGHT + SECTION_PADDING + SECTION_LABEL + ROW_HEIGHT / 2
    found = [
        Port(exchange_id=e.id, y=first + ROW_HEIGHT * min(n, found_fold.shown))
        for n, e in enumerate(inputs)
    ]
    output = (
        HEADER_HEIGHT
        + SECTION
        + ROW_HEIGHT * (found_fold.shown + _fold_row(found_fold))
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
