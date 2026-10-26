from __future__ import annotations

import uuid

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.geometry import Placement, Port, card_size, ports, shown_inputs
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, Database, ForegroundRef, SystemRef
from ecosemantic.routes import Label, Route
from ecosemantic.textmap import LEGEND, as_text

DATABASE = Database(
    name="d", elementary_flows="b", scheme="ecoinvent", version="1", system_model="cutoff"
)
LABEL = Label(x=-900, y=-900, width=50, height=16, per_unit="1 kg", scaled=None, formula=None)
FEED = uuid.uuid4()
METAL = uuid.uuid4()


def system() -> ProductSystem:
    def proc(code: str, exchanges: list[Exchange]) -> Process:
        return Process(
            id=uuid.uuid4(),
            code=code,
            name=code,
            unit="kg",
            location="GLO",
            reference_product=code,
            exchanges=exchanges,
        )

    a = proc("a", [Exchange(id=uuid.uuid4(), type="production", name="ore", amount=1, unit="kg")])
    b = proc(
        "b",
        [
            Exchange(id=METAL, type="production", name="metal", amount=1, unit="kg"),
            Exchange(
                id=FEED,
                type="product",
                name="ore feed",
                amount=2,
                unit="kg",
                input=ForegroundRef(code="a"),
            ),
        ],
    )
    return ProductSystem(id=uuid.uuid4(), name="s", database=DATABASE, processes=[a, b])


def placements(y_b: float = 0.0) -> list[Placement]:
    return [
        Placement(code="a", x=0, y=0, width=300, height=132, depth=1, output=97.0),
        Placement(
            code="b",
            x=420,
            y=y_b,
            width=300,
            height=154,
            depth=0,
            inputs=[Port(exchange_id=FEED, y=75.0)],
            outputs=[METAL],
            output=119.0,
        ),
    ]


def test_the_map_opens_with_its_legend_and_draws_each_card_with_its_code_and_rows() -> None:
    text = as_text(system(), placements(), [])
    assert text.splitlines()[0] == LEGEND
    assert "a" in text and "ore feed" in text


def test_an_arrow_ends_in_a_head_on_the_line_of_the_row_it_feeds() -> None:
    route = Route(
        provider="a",
        consumer="b",
        exchange_id=FEED,
        points=[(300, 97), (344, 97), (344, 75), (420, 75)],
        label=LABEL,
    )
    lines = as_text(system(), placements(), [route]).splitlines()[1:]
    assert "▶" in lines[int(75 // 11)]
    assert "#" not in "\n".join(lines)


def test_an_arrow_over_a_card_is_drawn_with_hashes() -> None:
    route = Route(
        provider="a",
        consumer="b",
        exchange_id=FEED,
        points=[(300, 97), (380, 97), (380, 40), (500, 40), (500, 75), (420, 75)],
        label=LABEL,
    )
    assert "#" in as_text(system(), placements(), [route])


def test_a_lane_below_a_card_leaves_its_box_closed() -> None:
    route = Route(
        provider="a",
        consumer="b",
        exchange_id=FEED,
        points=[(300, 97), (320, 97), (320, 166), (740, 166), (740, 200)],
        label=LABEL,
    )
    lines = as_text(system(), placements(), [route]).splitlines()[1:]
    bottom = int((154 - 0.001) // 11)
    assert "└" + "─" * 28 + "┘" in lines[bottom]
    assert "─" * 40 in lines[int(166 // 11)]
    assert "#" not in "\n".join(lines)


def test_a_route_with_bends_draws_corner_glyphs() -> None:
    route = Route(
        provider="a",
        consumer="b",
        exchange_id=FEED,
        points=[(300, 97), (344, 97), (344, 75), (420, 75)],
        label=LABEL,
    )
    text = as_text(system(), placements(), [route])
    assert "┘" in text and "┌" in text


def test_a_production_row_is_named_on_the_line_of_its_output_dot() -> None:
    lines = as_text(system(), placements(), []).splitlines()[1:]
    line = lines[int(119 // 11)]
    assert "metal" in line and line.rstrip().endswith("●")


def test_a_linked_systems_card_shows_its_dot_and_feeds_its_row() -> None:
    linked = f"system:{uuid.uuid4()}"
    cards = [
        Placement(code=linked, x=0, y=0, width=300, height=132, depth=1, output=66.0),
        placements()[1],
    ]
    route = Route(
        provider=linked,
        consumer="b",
        exchange_id=FEED,
        points=[(300, 66), (344, 66), (344, 75), (420, 75)],
        label=LABEL,
    )
    lines = as_text(system(), cards, [route]).splitlines()[1:]
    assert "●" in lines[int(66 // 11)]
    assert "▶" in lines[int(75 // 11)]


def scaled_cards() -> list[Placement]:
    a, b = placements()
    return [a, b.model_copy(update={"scaled": {METAL: 1.0, FEED: 2500.0}})]


def test_a_scaled_card_is_titled_with_its_written_production() -> None:
    lines = as_text(system(), scaled_cards(), []).splitlines()[1:]
    assert "┌ b · 1 kg ─" in lines[0]
    assert "┌ a ─" in lines[0]


def test_a_scaled_input_row_reads_its_name_then_its_written_amount() -> None:
    lines = as_text(system(), scaled_cards(), []).splitlines()[1:]
    assert "ore feed 2,500 kg" in lines[int(75 // 11)]


def test_a_scaled_output_row_keeps_its_right_alignment_with_the_amount_after_the_name() -> None:
    line = as_text(system(), scaled_cards(), []).splitlines()[1:][int(119 // 11)]
    assert "metal 1 kg ●" in line


def narrowed(width: int, code: str = "b") -> list[Placement]:
    return [p.model_copy(update={"width": width}) if p.code == code else p for p in scaled_cards()]


def test_a_scaled_input_row_shortens_its_name_and_keeps_its_amount_whole() -> None:
    line = as_text(system(), narrowed(170), []).splitlines()[1:][int(75 // 11)]
    assert "ore … 2,500 kg" in line


def test_a_scaled_row_shows_the_amount_alone_when_the_name_has_no_room() -> None:
    line = as_text(system(), narrowed(120), []).splitlines()[1:][int(75 // 11)]
    assert "│ 2,500 kg" in line and "ore" not in line


def test_a_scaled_output_row_keeps_its_amount_whole_and_stays_inside_the_box() -> None:
    line = as_text(system(), narrowed(120), []).splitlines()[1:][int(119 // 11)]
    assert "met… 1 kg ●" in line


def test_a_scaled_title_shortens_the_code_and_keeps_the_production_whole() -> None:
    cards = [
        p.model_copy(update={"code": "a_long_process_code", "width": 200}) if p.code == "b" else p
        for p in scaled_cards()
    ]
    top = as_text(system(), cards, []).splitlines()[1]
    assert "· 1 kg" in top and "…" in top and "a_long_process_code" not in top


def linking() -> tuple[ProductSystem, str]:
    """The system with b's ore feed taken from another system's functional unit."""
    other = uuid.uuid4()
    linked = system()
    linked.process("b").exchanges[1].input = SystemRef(product_system_id=other, at_hash="h")
    return linked, f"system:{other}"


def test_a_linked_card_in_the_scaled_view_is_titled_with_its_scaled_output() -> None:
    linked, code = linking()
    card = Placement(
        code=code, x=0, y=0, width=300, height=132, depth=1, output=66.0, scaled={METAL: 2.0}
    )
    lines = as_text(linked, [card, scaled_cards()[1]], []).splitlines()[1:]
    assert lines[0].split("┐")[0].endswith("… · 2 kg ")
    assert "●" in lines[int(66 // 11)]


def test_a_linked_card_without_its_one_scaled_output_is_refused() -> None:
    linked, code = linking()
    card = Placement(code=code, x=0, y=0, width=300, height=132, depth=1, output=66.0, scaled={})
    with pytest.raises(Invalid, match="carries 0 scaled amounts"):
        as_text(linked, [card, scaled_cards()[1]], [])


def test_an_unscaled_card_shows_the_name_alone() -> None:
    text = as_text(system(), placements(), [])
    assert "ore feed kg" not in text and "ore feed " in text + " "
    assert "·" not in text


def _wide_card(count: int) -> tuple[ProductSystem, list[Placement]]:
    """One card with `count` inputs, placed as the layout places it."""
    inputs = [
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name=f"i{n}",
            amount=1.0,
            unit="kg",
            input=BackgroundRef(database="d", id=f"b{n}"),
        )
        for n in range(count)
    ]
    production = Exchange(id=uuid.uuid4(), type="production", name="p", amount=1.0, unit="kg")
    process = Process(
        id=uuid.uuid4(),
        code="p",
        name="p",
        unit="kg",
        location="GLO",
        reference_product="p",
        exchanges=[production, *inputs],
    )
    system = ProductSystem(id=uuid.uuid4(), name="s", database=DATABASE, processes=[process])
    width, height = card_size(process, {})
    found, output = ports(process, {})
    card = Placement(
        code="p",
        x=0,
        y=0,
        width=width,
        height=height,
        depth=0,
        shown_inputs=shown_inputs(process, {}),
        inputs=found,
        output=output,
    )
    return system, [card]


def test_a_card_with_ten_inputs_draws_six_rows_and_a_fold_row() -> None:
    system, cards = _wide_card(10)
    lines = as_text(system, cards, []).splitlines()
    assert all(any(f"i{n}" in line for line in lines) for n in range(6))
    assert any("4 more inputs" in line for line in lines)
    assert not any(f"i{n}" in line for n in range(6, 10) for line in lines)
    fold = next(n for n, line in enumerate(lines) if "4 more inputs" in line)
    last = next(n for n, line in enumerate(lines) if "i5" in line)
    assert fold > last


def test_a_card_with_six_inputs_draws_no_fold_row() -> None:
    system, cards = _wide_card(6)
    text = as_text(system, cards, [])
    assert all(f"i{n}" in text for n in range(6))
    assert "more inputs" not in text
