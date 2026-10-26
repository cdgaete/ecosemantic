from __future__ import annotations

import uuid

import pytest

import ecosemantic.layout as layout_module
from ecosemantic.errors import Invalid
from ecosemantic.geometry import (
    CARD_WIDTH,
    COLUMN_GAP,
    FOLD_AFTER,
    HEADER_HEIGHT,
    LINKED_HEIGHT,
    ROW_GAP,
    ROW_HEIGHT,
    SECTION,
    Link,
    LinkText,
    Placement,
    card_size,
    link_texts,
    links,
    ports,
    shown_inputs,
)
from ecosemantic.layout import arrange, depths
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
)
from ecosemantic.model.validation import anchors, roots
from ecosemantic.ports.types import Side
from ecosemantic.routes import Route
from ecosemantic.routes import route as routed
from ecosemantic.troubles import score, troubles

DATABASE = Database(
    name="d", elementary_flows="b", scheme="ecoinvent", version="1", system_model="cutoff"
)


def process(code: str, inputs: list[str] | None = None, extra: int = 0) -> Process:
    """A process with one production output, one foreground input per code, and `extra`
    background inputs that name nothing."""
    exchanges = [Exchange(id=uuid.uuid4(), type="production", name=code, amount=1.0, unit="kg")]
    exchanges += [
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name=code_in,
            amount=1.0,
            unit="kg",
            input=ForegroundRef(code=code_in),
        )
        for code_in in inputs or []
    ]
    exchanges += [
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name=f"b{n}",
            amount=1.0,
            unit="kg",
            input=BackgroundRef(database="d", id=f"b{n}"),
        )
        for n in range(extra)
    ]
    return Process(
        id=uuid.uuid4(),
        code=code,
        name=code,
        unit="kg",
        location="GLO",
        reference_product=code,
        exchanges=exchanges,
    )


def system(*processes: Process) -> ProductSystem:
    return ProductSystem(id=uuid.uuid4(), name="s", database=DATABASE, processes=list(processes))


def emitted(drawn: ProductSystem) -> dict[str, Side]:
    """Every elementary flow of a system on the output side, for tests about placement."""
    return {
        e.input.id: "output"
        for p in drawn.processes
        for e in p.exchanges
        if isinstance(e.input, ElementaryFlowRef)
    }


def test_a_card_grows_by_a_row_an_exchange() -> None:
    one = card_size(process("a"), {})
    two = card_size(process("a", extra=1), {})
    assert two[1] - one[1] == ROW_HEIGHT
    assert one[0] == two[0]


def test_a_card_folds_its_inputs_and_gains_one_row_for_the_fold() -> None:
    folded = card_size(process("a", extra=FOLD_AFTER), {})
    past = card_size(process("a", extra=FOLD_AFTER + 4), {})
    # the fold row replaces every input past the fold, whatever their number
    assert past[1] - folded[1] == ROW_HEIGHT


def test_the_reference_is_the_zero_column_and_its_providers_are_deeper() -> None:
    built = system(process("fu", ["mid"]), process("mid", ["raw"]), process("raw"))
    assert depths(built, ["fu"]) == {"fu": 0, "mid": 1, "raw": 2}


def test_a_placement_carries_the_row_height() -> None:
    built = system(process("fu", ["a"]), process("a"))
    assert all(p.row_height == ROW_HEIGHT for p in arrange(built, ["fu"], {}, emitted(built)))


def test_the_longest_path_wins_when_a_process_feeds_two_depths() -> None:
    built = system(process("fu", ["mid", "raw"]), process("mid", ["raw"]), process("raw"))
    # raw feeds the reference directly and through mid; the deeper placement is the one drawn
    assert depths(built, ["fu"])["raw"] == 2


def test_a_process_the_walk_never_reaches_sits_past_the_deepest() -> None:
    built = system(process("fu", ["mid"]), process("mid"), process("loose"))
    assert depths(built, ["fu"])["loose"] == 2


def test_every_root_is_a_zero_column_and_what_feeds_them_is_deeper() -> None:
    built = system(
        process("fu1", ["shared"]),
        process("fu2", ["shared"]),
        process("shared", ["raw"]),
        process("raw"),
    )
    assert depths(built, ["fu1", "fu2"]) == {"fu1": 0, "fu2": 0, "shared": 1, "raw": 2}


def test_a_cycle_does_not_hang_and_every_process_gets_a_column() -> None:
    built = system(process("fu", ["a"]), process("a", ["b"]), process("b", ["a"]))
    found = depths(built, ["fu"])
    assert set(found) == {"fu", "a", "b"}
    assert found["fu"] == 0


def overlapping(placements: list[Placement]) -> list[tuple[str, str]]:
    """Every pair of cards whose rectangles meet, with the row gap counted as part of a card."""
    found = []
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            if a.x < b.x + b.width and b.x < a.x + a.width:
                if a.y < b.y + b.height + ROW_GAP and b.y < a.y + a.height + ROW_GAP:
                    found.append((a.code, b.code))
    return found


def test_the_reference_is_rightmost_and_its_providers_are_to_the_left() -> None:
    built = system(process("fu", ["mid"]), process("mid", ["raw"]), process("raw"))
    placed = {p.code: p for p in arrange(built, ["fu"], {}, emitted(built))}
    assert placed["fu"].x > placed["mid"].x > placed["raw"].x
    assert placed["fu"].x - placed["mid"].x == CARD_WIDTH + COLUMN_GAP


def test_the_reference_sits_at_the_middle_height() -> None:
    built = system(process("fu", ["a", "b", "c"]), process("a"), process("b"), process("c"))
    placed = {p.code: p for p in arrange(built, ["fu"], {}, emitted(built))}
    suppliers = [placed[c] for c in ("a", "b", "c")]
    top = min(p.y for p in suppliers)
    bottom = max(p.y + p.height for p in suppliers)
    middle = placed["fu"].y + placed["fu"].height / 2
    assert abs(middle - (top + bottom) / 2) < 1.0


def test_no_two_cards_overlap_however_uneven_their_sizes() -> None:
    built = system(
        process("fu", ["a", "b", "c", "d"]),
        process("a", extra=30),
        process("b"),
        process("c", extra=12),
        process("d", extra=1),
    )
    assert overlapping(arrange(built, ["fu"], {}, emitted(built))) == []


def test_a_held_card_keeps_its_place_and_the_others_pack_around_it() -> None:
    built = system(process("fu", ["a", "b"]), process("a"), process("b"))
    placed = {p.code: p for p in arrange(built, ["fu"], {"a": (0.0, 600.0)}, emitted(built))}
    assert (placed["a"].x, placed["a"].y) == (0.0, 600.0)
    assert placed["a"].held and not placed["b"].held
    assert overlapping(list(placed.values())) == []


def test_a_held_card_in_a_permuted_column_keeps_its_place_and_the_rest_pack_around_it() -> None:
    built = system(
        process("fu", ["a", "b", "c", "d"]),
        process("a", extra=2),
        process("b", extra=1),
        process("c", extra=4),
        process("d"),
    )
    placed = {p.code: p for p in arrange(built, ["fu"], {"b": (0.0, 200.0)}, emitted(built))}
    assert (placed["b"].x, placed["b"].y) == (0.0, 200.0) and placed["b"].held
    assert not any(placed[code].held for code in ("a", "c", "d"))
    assert {placed[code].x for code in ("a", "c", "d")} == {0.0}
    assert overlapping(list(placed.values())) == []


def test_a_process_added_beside_a_held_card_does_not_move_it() -> None:
    before = system(process("fu", ["a"]), process("a"))
    held = {"a": (0.0, 600.0)}
    after = system(process("fu", ["a", "b"]), process("a"), process("b"))
    first = {p.code: p for p in arrange(before, ["fu"], held, emitted(before))}
    second = {p.code: p for p in arrange(after, ["fu"], held, emitted(after))}
    assert (first["a"].x, first["a"].y) == (second["a"].x, second["a"].y)
    assert overlapping(list(second.values())) == []


def test_a_card_no_anchor_reaches_sits_left_of_every_column() -> None:
    built = system(process("fu", ["a"]), process("a"), process("loose"))
    placed = {p.code: p for p in arrange(built, ["fu"], {}, emitted(built))}
    assert placed["loose"].x < placed["a"].x


async def test_nothing_overlaps_on_a_stored_product_system(
    fixture_system_stored: ProductSystem,
) -> None:
    placed = arrange(
        fixture_system_stored, roots(fixture_system_stored), {}, emitted(fixture_system_stored)
    )
    assert {p.code for p in placed} == {p.code for p in fixture_system_stored.processes}
    assert overlapping(placed) == []


def test_a_held_card_shadows_the_column_its_position_falls_in() -> None:
    built = system(process("fu", ["mid"]), process("mid", ["raw"]), process("raw"))
    placed = {p.code: p for p in arrange(built, ["fu"], {"mid": (0.0, 40.0)}, emitted(built))}
    assert overlapping(list(placed.values())) == []


def test_a_deeper_column_is_ordered_by_its_consumers_in_the_column_before_it() -> None:
    built = system(
        process("fu", ["L", "R"]),
        process("L", ["b"]),
        process("R", ["a"]),
        process("a"),
        process("b"),
    )
    placed = {p.code: p for p in arrange(built, ["fu"], {}, emitted(built))}
    assert placed["b"].y < placed["a"].y


def test_a_system_with_two_roots_draws_its_supply_chain_to_their_left() -> None:
    built = system(process("fu1", ["shared"]), process("fu2", ["shared"]), process("shared"))
    placed = {p.code: p for p in arrange(built, roots(built), {}, emitted(built))}
    assert placed["fu1"].x == placed["fu2"].x > placed["shared"].x
    assert overlapping(list(placed.values())) == []


def test_a_root_that_consumes_its_own_product_keeps_its_supply_chain_to_its_left() -> None:
    built = system(process("fu", ["fu", "plant"]), process("plant", ["fuel"]), process("fuel"))
    placed = {p.code: p for p in arrange(built, roots(built), {}, emitted(built))}
    assert placed["fu"].x > placed["plant"].x > placed["fuel"].x


def test_an_edge_from_a_process_to_itself_is_not_named_backwards() -> None:
    built = system(process("fu", ["fu", "plant"]), process("plant"))
    placed = arrange(built, roots(built), {}, emitted(built))
    found = troubles(placed, routed(placed, links(built), link_texts(built, None)))
    assert "edge_backwards" not in [t.kind for t in found]


def test_a_functional_unit_inside_a_loop_is_laid_out_from_its_reference(
    product_system: ProductSystem,
) -> None:
    looped = product_system.model_copy(deep=True)
    looped.process("fabric").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="tshirt",
            amount=2.0,
            unit="unit",
            input=ForegroundRef(code="tshirt"),
        )
    )
    placed = {p.code: p for p in arrange(looped, anchors(looped), {}, emitted(looped))}
    assert placed["tshirt"].x > placed["fabric"].x > placed["yarn"].x


def linking(code: str, target: uuid.UUID, inputs: list[str] | None = None) -> Process:
    """A process with a foreground input per code and one unit of a linked system."""
    made = process(code, inputs)
    made.exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="part",
            amount=1.0,
            unit="unit",
            input=SystemRef(product_system_id=target, at_hash="a" * 64),
        )
    )
    return made


def test_a_linked_system_is_one_card_a_column_beyond_its_deepest_consumer() -> None:
    part = uuid.uuid4()
    built = system(linking("fu", part, ["mid"]), linking("mid", part))
    placed = {p.code: p for p in arrange(built, ["fu"], {}, {})}
    card = placed[f"system:{part}"]
    assert [p.code for p in placed.values()].count(f"system:{part}") == 1
    # mid sits one column left of fu; the linked card one beyond mid
    assert card.depth == placed["mid"].depth + 1 == 2
    assert card.height == LINKED_HEIGHT
    assert card.shown_inputs == 0
    held = {p.code: p for p in arrange(built, ["fu"], {f"system:{part}": (900.0, 900.0)}, {})}
    assert (held[f"system:{part}"].x, held[f"system:{part}"].y) == (900.0, 900.0)
    pairs = [(k.provider, k.consumer) for k in links(built)]
    assert (f"system:{part}", "mid") in pairs and (f"system:{part}", "fu") in pairs


def test_a_card_counts_resources_among_its_inputs_and_emissions_among_its_outputs() -> None:
    made = process("fu", extra=1)
    for flow in ("water", "co2"):
        made.exchanges.append(
            Exchange(
                id=uuid.uuid4(),
                type="elementary",
                name=flow,
                amount=1.0,
                unit="kg",
                input=ElementaryFlowRef(database="b", id=flow),
            )
        )
    sides = {"water": "input", "co2": "output"}
    assert shown_inputs(made, sides) == 2
    # production and the emission are outputs, the background input and the resource inputs
    assert card_size(made, sides)[1] == HEADER_HEIGHT + 2 * SECTION + ROW_HEIGHT * 4


def test_a_placement_carries_its_rows_anchors_and_output() -> None:
    feeder = process("a")
    consumer = process("b", ["a"])
    drawn = system(feeder, consumer)
    placed = {p.code: p for p in arrange(drawn, ["b"], {}, emitted(drawn))}
    assert [p.exchange_id for p in placed["b"].inputs] == [consumer.exchanges[1].id]
    assert placed["a"].output == ports(feeder, {})[1]
    assert placed["b"].outputs == [consumer.exchanges[0].id]


def test_the_arrangement_keeps_a_hub_feeding_many_columns_from_running_arrows_through_cards() -> (
    None
):
    hub = process("hub")
    water = process("water", ["hub"])
    mine = process("mine", ["hub"])
    plant = process("plant", ["mine", "water", "hub"])
    move = process("move", ["plant"])
    smelt = process("smelt", ["move", "hub"])
    refine = process("refine", ["smelt", "hub"])
    drawn = system(hub, water, mine, plant, move, smelt, refine)
    placed = arrange(drawn, ["refine"], {}, emitted(drawn))
    found = troubles(placed, routed(placed, links(drawn), link_texts(drawn, None)))
    assert [t for t in found if t.kind in ("edge_through_card", "cards_overlap")] == []


def hub_system() -> ProductSystem:
    hub = process("hub")
    water = process("water", ["hub"])
    mine = process("mine", ["hub"])
    plant = process("plant", ["mine", "water", "hub"])
    move = process("move", ["plant"])
    smelt = process("smelt", ["move", "hub"])
    refine = process("refine", ["smelt", "hub"])
    return system(hub, water, mine, plant, move, smelt, refine)


def test_arrange_measures_labels_at_their_scaled_width(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn = hub_system()
    amounts = {p.code: {e.id: 123456789012.0 for e in p.exchanges} for p in drawn.processes}
    seen: list[dict[uuid.UUID, LinkText]] = []
    real = layout_module.route

    def spy(
        placements: list[Placement],
        drawn_links: list[Link],
        texts: dict[uuid.UUID, LinkText],
    ) -> list[Route]:
        seen.append(dict(texts))
        return real(placements, drawn_links, texts)

    monkeypatch.setattr(layout_module, "route", spy)
    placed = arrange(drawn, ["refine"], {}, emitted(drawn), amounts)
    assert seen and all(t[1] == "123,000,000,000 kg" for texts in seen for t in texts.values())
    monkeypatch.setattr(layout_module, "route", real)
    texts = link_texts(drawn, amounts)
    plain = arrange(drawn, ["refine"], {}, emitted(drawn))

    def scored(cards: list[Placement]) -> int:
        return score(troubles(cards, routed(cards, links(drawn), texts)))

    assert scored(placed) <= scored(plain)


def test_a_missing_scaled_card_is_named() -> None:
    drawn = hub_system()
    with pytest.raises(Invalid, match="hub"):
        link_texts(drawn, {})


def test_a_missing_scaled_exchange_is_named() -> None:
    drawn = hub_system()
    amounts = {p.code: {e.id: 1.0 for e in p.exchanges} for p in drawn.processes}
    missing = drawn.processes[0].exchanges[0].id
    del amounts["hub"][missing]
    with pytest.raises(Invalid, match=str(missing)):
        link_texts(drawn, amounts)


def test_link_texts_carry_a_formula_text_for_a_formula_exchange_only() -> None:
    drawn = system(process("a"), process("b", ["a"]))
    plain, formula = drawn.processes[1].exchanges[1], drawn.processes[0].exchanges[0]
    drawn.processes[1].exchanges[1] = plain.model_copy(update={"unit": "kWh", "formula": "2 * x"})
    texts = link_texts(drawn, None)
    assert texts[plain.id].formula == "ƒ kWh"
    assert texts[formula.id].formula is None
