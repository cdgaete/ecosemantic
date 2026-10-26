"""The drawing an agent reads: every card and every arrow of the canvas in characters, one
character per 10 px across and one line per 11 px down."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable

from ecosemantic.errors import Invalid
from ecosemantic.geometry import FOLD_AFTER, ROW_HEIGHT, Placement, linked_code
from ecosemantic.model.entities import Exchange, ProductSystem
from ecosemantic.model.refs import SystemRef
from ecosemantic.quantity import written
from ecosemantic.routes import Route
from ecosemantic.troubles import passes_through

SCALE_X = 10.0
SCALE_Y = ROW_HEIGHT / 2
LEGEND = (
    "1 char = 10 px across, 1 line = 11 px down; ● a card's output, ▶ an arrow entering an "
    "input row, ┼ two arrows crossing, # an arrow over a card"
)
GLYPHS: dict[frozenset[str], str] = {
    frozenset("LR"): "─",
    frozenset("UD"): "│",
    frozenset("RD"): "┌",
    frozenset("LD"): "┐",
    frozenset("RU"): "└",
    frozenset("LU"): "┘",
    frozenset("LRD"): "┬",
    frozenset("LRU"): "┴",
    frozenset("UDR"): "├",
    frozenset("UDL"): "┤",
    frozenset("LRUD"): "┼",
}
STEPS = {(-1, 0): "U", (1, 0): "D", (0, -1): "L", (0, 1): "R"}


def _glyph(directions: frozenset[str]) -> str:
    if len(directions) == 1:
        return "─" if directions <= {"L", "R"} else "│"
    return GLYPHS[directions]


def _cells(
    points: list[tuple[float, float]], col: Callable[[float], int], row: Callable[[float], int]
) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if y0 == y1:
            line, a, b = row(y0), col(x0), col(x1)
            step = 1 if b >= a else -1
            run = [(line, c) for c in range(a, b + step, step)]
        else:
            c, a, b = col(x0), row(y0), row(y1)
            step = 1 if b >= a else -1
            run = [(line, c) for line in range(a, b + step, step)]
        for cell in run:
            if not cells or cells[-1] != cell:
                cells.append(cell)
    return cells


def _box(grid: list[list[str]], c0: int, c1: int, l0: int, l1: int, title: str) -> None:
    for line in range(l0, l1 + 1):
        for col in range(c0, c1 + 1):
            top, bottom = line == l0, line == l1
            left, right = col == c0, col == c1
            if (top or bottom) and (left or right):
                grid[line][col] = "┌┐└┘"[(2 if bottom else 0) + (1 if right else 0)]
            elif top or bottom:
                grid[line][col] = "─"
            elif left or right:
                grid[line][col] = "│"
            else:
                grid[line][col] = " "
    for n, ch in enumerate(f" {title} "[: max(c1 - c0 - 1, 0)]):
        grid[l0][c0 + 1 + n] = ch


def _write(grid: list[list[str]], line: int, c0: int, c1: int, text: str) -> None:
    for n, ch in enumerate(text[: max(c1 - c0 - 2, 0)]):
        grid[line][c0 + 2 + n] = ch


def _write_right(grid: list[list[str]], line: int, c0: int, c1: int, text: str) -> None:
    room = max(c1 - c0 - 2, 0)
    shown = text[:room]
    start = c1 - 1 - len(shown)
    for n, ch in enumerate(shown):
        grid[line][start + n] = ch


def _fit(name: str, separator: str, amount: str, room: int) -> str:
    """The name and the amount joined by the separator, the amount whole and the name shortened
    with `…` to fit the room; the amount alone when the name has no room."""
    if len(name) + len(separator) + len(amount) <= room:
        return f"{name}{separator}{amount}"
    name_room = room - len(separator) - len(amount)
    if name_room < 1:
        return amount
    return f"{name[: name_room - 1]}…{separator}{amount}"


def _row_text(placement: Placement, exchange: Exchange, room: int) -> str:
    if placement.scaled is None:
        return exchange.name
    amount = written(placement.scaled[exchange.id], exchange.unit)
    return _fit(exchange.name, " ", amount, room)


def _title(
    placement: Placement,
    exchanges: dict[uuid.UUID, Exchange],
    linked_units: dict[str, str],
    room: int,
) -> str:
    """A card's code, with its scaled output when the drawing is scaled: a process's production,
    or a linked system's output in the unit its link takes it in."""
    if placement.scaled is None:
        return placement.code
    if placement.code in linked_units:
        if len(placement.scaled) != 1:
            raise Invalid(
                f"linked card {placement.code} carries {len(placement.scaled)} scaled amounts; "
                "it holds its reference process's output alone"
            )
        [output] = placement.scaled.values()
        amount = written(output, linked_units[placement.code])
    elif placement.outputs:
        production = exchanges[placement.outputs[0]]
        amount = written(placement.scaled[production.id], production.unit)
    else:
        return placement.code
    return _fit(placement.code, " · ", amount, room)


def as_text(system: ProductSystem, placements: list[Placement], routes: list[Route]) -> str:
    """The legend, then the canvas: cards as boxes titled by code, and by scaled output when
    scaled, with the first `FOLD_AFTER` input rows named and one row reading how many inputs sit
    behind the fold; arrows in box-drawing characters, `▶` on the row an arrow feeds, `┼` where
    arrows of two providers cross, `#` where an arrow runs over a card."""
    if not placements:
        return LEGEND + "\n(no processes)"
    xs = [p.x for p in placements] + [p.x + p.width for p in placements]
    ys = [p.y for p in placements] + [p.y + p.height for p in placements]
    for r in routes:
        xs += [x for x, _ in r.points]
        ys += [y for _, y in r.points]
    left, top = min(xs), min(ys)
    width = math.ceil((max(xs) - left) / SCALE_X) + 1
    height = math.floor((max(ys) - top) / SCALE_Y) + 1

    def col(x: float) -> int:
        return round((x - left) / SCALE_X)

    def row(y: float) -> int:
        return math.floor((y - top) / SCALE_Y)

    grid = [[" "] * width for _ in range(height)]
    owner: dict[tuple[int, int], str] = {}
    exchanges = {e.id: e for p in system.processes for e in p.exchanges}
    linked_units = {
        linked_code(e.input): e.unit
        for p in system.processes
        for e in p.exchanges
        if isinstance(e.input, SystemRef)
    }
    for p in placements:
        c0, c1 = col(p.x), col(p.x + p.width) - 1
        l0, l1 = row(p.y), row(p.y + p.height - 0.001)
        _box(grid, c0, c1, l0, l1, _title(p, exchanges, linked_units, c1 - c0 - 3))
        for line in range(l0, l1 + 1):
            for c in range(c0, c1 + 1):
                owner[(line, c)] = p.code
        for port in p.inputs[:FOLD_AFTER]:
            _write(
                grid,
                row(p.y + port.y),
                c0,
                c1,
                _row_text(p, exchanges[port.exchange_id], c1 - c0 - 2),
            )
        if len(p.inputs) > FOLD_AFTER:
            _write(
                grid,
                row(p.y + p.inputs[FOLD_AFTER].y),
                c0,
                c1,
                f"{len(p.inputs) - FOLD_AFTER} more inputs",
            )
        for n, exchange_id in enumerate(p.outputs):
            _write_right(
                grid,
                row(p.y + p.output + n * ROW_HEIGHT),
                c0,
                c1,
                _row_text(p, exchanges[exchange_id], c1 - c0 - 2),
            )
        grid[row(p.y + p.output)][c1] = "●"
    drawn: dict[tuple[int, int], tuple[str, frozenset[str]]] = {}
    for r in routes:
        cells = _cells(r.points, col, row)
        for (a, b), (x, y) in zip(r.points, r.points[1:], strict=False):
            for p in placements:
                if passes_through(((a, b), (x, y)), p):
                    for cell in _cells([(a, b), (x, y)], col, row):
                        if owner.get(cell) == p.code:
                            grid[cell[0]][cell[1]] = "#"
        for n, (line, c) in enumerate(cells):
            if n == len(cells) - 1 or (line, c) in owner:
                continue
            directions = set()
            for m in (n - 1, n + 1):
                if 0 <= m < len(cells):
                    directions.add(STEPS[(cells[m][0] - line, cells[m][1] - c)])
            own = frozenset(directions)
            previous = drawn.get((line, c))
            if previous is None:
                grid[line][c] = _glyph(own)
                drawn[(line, c)] = (r.provider, own)
            elif previous[0] == r.provider:
                merged = previous[1] | own
                grid[line][c] = _glyph(merged)
                drawn[(line, c)] = (r.provider, merged)
            elif previous[1] != own:
                grid[line][c] = "┼"
        line, c = cells[-1]
        grid[line][c] = "▶"
    return "\n".join([LEGEND] + ["".join(line).rstrip() for line in grid])
