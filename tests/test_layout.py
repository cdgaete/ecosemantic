from __future__ import annotations

import uuid

import pytest
from fastmcp import Client, FastMCP

import ecosemantic.layout as layout_module
from ecosemantic.errors import Invalid
from ecosemantic.geometry import (
    CARD_WIDTH,
    COLUMN_GAP,
    COLUMN_TOP,
    FOLD_AFTER,
    HEADER_HEIGHT,
    LINKED_HEIGHT,
    ROW_GAP,
    ROW_HEIGHT,
    SECTION,
    SECTION_LABEL,
    SECTION_PADDING,
    Link,
    LinkText,
    Placement,
    Region,
    SharedSupplier,
    card_geometry,
    card_size,
    link_texts,
    links,
    ports,
    shown_inputs,
)
from ecosemantic.layout import (
    REGION_PAD,
    arrange,
    card_stages,
    depths,
    nodes,
    shared_suppliers,
    stage_regions,
)
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
)
from ecosemantic.model.stages import stage_order
from ecosemantic.model.validation import anchors, roots
from ecosemantic.ports.types import Side
from ecosemantic.routes import Route
from ecosemantic.routes import route as routed
from ecosemantic.troubles import score, troubles
from tests.layout_fixtures import hundred, staged_nine

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


async def test_the_arrangement_carries_the_card_geometry(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        ).structured_content["value"]
    card = card_geometry()
    assert answer["card"] == card.model_dump()
    assert (
        card.width,
        card.header_height,
        card.section_padding,
        card.section_label,
        card.row_height,
    ) == (CARD_WIDTH, HEADER_HEIGHT, SECTION_PADDING, SECTION_LABEL, ROW_HEIGHT)
    assert all("row_height" not in placement for placement in answer["cards"])


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


def test_a_held_card_in_the_reference_column_keeps_the_reference_clear_of_it() -> None:
    built = system(process("fu", ["a", "b"]), process("a"), process("b"))
    column = CARD_WIDTH + COLUMN_GAP
    held = {"a": (column, COLUMN_TOP)}
    placed = {p.code: p for p in arrange(built, ["fu"], held, emitted(built))}
    assert (placed["a"].x, placed["a"].y) == (column, COLUMN_TOP)
    assert not placed["fu"].held
    assert overlapping(list(placed.values())) == []


def test_a_held_card_outside_the_reference_column_leaves_the_reference_at_the_middle() -> None:
    built = system(process("fu", ["a", "b", "c"]), process("a"), process("b"), process("c"))
    far = 2 * (CARD_WIDTH + COLUMN_GAP)
    placed = {p.code: p for p in arrange(built, ["fu"], {"a": (far, COLUMN_TOP)}, emitted(built))}
    assert (placed["a"].x, placed["a"].y) == (far, COLUMN_TOP)
    suppliers = [placed[c] for c in ("a", "b", "c")]
    top = min(p.y for p in suppliers)
    bottom = max(p.y + p.height for p in suppliers)
    middle = placed["fu"].y + placed["fu"].height / 2
    assert abs(middle - (top + bottom) / 2) < 1.0


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


def test_the_drawing_s_columns_and_arrows_come_from_one_edge_set() -> None:
    part = uuid.uuid4()
    mid = linking("mid", part, ["fu"])
    mid.exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="part",
            amount=2.0,
            unit="unit",
            input=SystemRef(product_system_id=part, at_hash="a" * 64),
        )
    )
    built = system(process("fu", ["ghost"]), mid)
    drawn = [
        (provider, consumer)
        for consumer, providers in nodes(built).items()
        for provider in providers
    ]
    arrows = [(k.provider, k.consumer) for k in links(built)]
    assert drawn == list(dict.fromkeys(arrows))


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


def tagged(made: Process, stage: str) -> Process:
    """The process, carrying a life-cycle stage."""
    made.metadata["life_cycle_stage"] = stage
    return made


def water_chain() -> ProductSystem:
    """Bottled water walked home, one process and one life-cycle stage per step."""
    return system(
        tagged(process("drinking_water", ["bottled_home"]), "use"),
        tagged(process("bottled_home", ["bottled_retail"]), "distribution and end of life"),
        tagged(process("bottled_retail", ["bottled_plant"]), "distribution"),
        tagged(process("bottled_plant", ["pet_bottle"]), "production"),
        tagged(process("pet_bottle"), "packaging"),
    )


def copper() -> ProductSystem:
    """The copper chain, its shared supplier `sen` feeding every step of it."""
    return system(
        tagged(process("refinery", ["smelter", "sen"]), "smelting and refining"),
        tagged(process("smelter", ["transport", "sen"]), "smelting and refining"),
        tagged(process("transport", ["concentrator"]), "transport"),
        tagged(process("concentrator", ["mine", "desal", "sen"]), "concentration"),
        tagged(process("mine", ["sen"]), "extraction"),
        tagged(process("desal", ["sen"]), "concentration"),
        process("sen"),
    )


def test_a_system_without_stages_is_arranged_as_before(
    fixture_system_stored: ProductSystem,
) -> None:
    plain = arrange(
        fixture_system_stored,
        roots(fixture_system_stored),
        {},
        emitted(fixture_system_stored),
    )
    cleared = fixture_system_stored.model_copy(deep=True)
    for made in cleared.processes:
        made.metadata["life_cycle_stage"] = None
    blanked = fixture_system_stored.model_copy(deep=True)
    for made in blanked.processes:
        made.metadata["life_cycle_stage"] = "  "
    assert arrange(cleared, roots(cleared), {}, emitted(cleared)) == plain
    assert arrange(blanked, roots(blanked), {}, emitted(blanked)) == plain


def test_each_stage_takes_a_band_of_its_own_from_the_functional_unit() -> None:
    drawn = water_chain()
    placed = {p.code: p for p in arrange(drawn, ["drinking_water"], {}, emitted(drawn))}
    walked = [
        placed[code].x
        for code in (
            "drinking_water",
            "bottled_home",
            "bottled_retail",
            "bottled_plant",
            "pet_bottle",
        )
    ]
    assert walked == sorted(walked, reverse=True)
    assert len(set(walked)) == len(walked)


def test_a_stage_keeps_its_band_where_distance_disagrees() -> None:
    drawn = copper()
    placed = {p.code: p for p in arrange(drawn, ["refinery"], {}, emitted(drawn))}
    pitch = CARD_WIDTH + COLUMN_GAP
    # desal sits a column further from the reference than concentrator by distance
    assert abs(placed["desal"].x - placed["concentrator"].x) == pitch
    assert placed["concentrator"].x > placed["mine"].x
    assert placed["desal"].x > placed["mine"].x
    # the column states the stage; the depth stays the distance the two cards share
    assert placed["desal"].depth == placed["mine"].depth == 4


def test_a_shared_supplier_sits_in_the_band_of_no_stage() -> None:
    drawn = copper()
    placed = arrange(drawn, ["refinery"], {}, emitted(drawn))
    assert min(placed, key=lambda card: card.x).code == "sen"


def test_a_linked_card_takes_the_stage_of_the_process_taking_it() -> None:
    part = uuid.uuid4()
    one = system(tagged(linking("fu", part), "a"))
    assert card_stages(one) == {"fu": "a", f"system:{part}": "a"}
    two = system(tagged(linking("fu", part), "a"), tagged(linking("mid", part), "b"))
    assert card_stages(two)[f"system:{part}"] is None


def meets(a: Region, b: Region) -> bool:
    """Whether two regions share any area."""
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height
        and b.y < a.y + a.height
    )


def holds(region: Region, card: Placement) -> bool:
    """Whether a region encloses a card's rectangle."""
    return (
        region.x <= card.x
        and region.y <= card.y
        and card.x + card.width <= region.x + region.width
        and card.y + card.height <= region.y + region.height
    )


def test_each_stage_answers_one_region_and_none_overlap() -> None:
    drawn = water_chain()
    placed = arrange(drawn, ["drinking_water"], {}, emitted(drawn))
    found = stage_regions(drawn, placed)
    assert [s.stage for s in found] == [
        "use",
        "distribution and end of life",
        "distribution",
        "production",
        "packaging",
    ]
    assert [s.codes for s in found] == [
        ["drinking_water"],
        ["bottled_home"],
        ["bottled_retail"],
        ["bottled_plant"],
        ["pet_bottle"],
    ]
    assert all(len(s.regions) == 1 for s in found)
    boxes = [s.regions[0] for s in found]
    assert [(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1 :] if meets(a, b)] == []
    cards = {p.code: p for p in placed}
    for entry in found:
        assert holds(entry.regions[0], cards[entry.codes[0]])


def test_a_stage_split_by_distance_answers_one_region() -> None:
    drawn = copper()
    placed = arrange(drawn, ["refinery"], {}, emitted(drawn))
    found = {s.stage: s for s in stage_regions(drawn, placed)}
    assert set(found) == {"smelting and refining", "transport", "concentration", "extraction"}
    concentration = found["concentration"]
    assert concentration.codes == ["concentrator", "desal"]
    assert len(concentration.regions) == 1
    cards = {p.code: p for p in placed}
    assert holds(concentration.regions[0], cards["concentrator"])
    assert holds(concentration.regions[0], cards["desal"])
    assert not any("sen" in entry.codes for entry in found.values())


def test_a_held_card_away_from_its_stage_has_a_region_of_its_own() -> None:
    drawn = water_chain()
    far = 5 * (CARD_WIDTH + COLUMN_GAP)
    held = {"pet_bottle": (far, COLUMN_TOP)}
    placed = arrange(drawn, ["drinking_water"], held, emitted(drawn))
    card = next(p for p in placed if p.code == "pet_bottle")
    assert (card.x, card.y, card.held) == (far, COLUMN_TOP, True)
    found = {s.stage: s for s in stage_regions(drawn, placed)}
    packaging = found["packaging"]
    assert packaging.codes == ["pet_bottle"]
    assert len(packaging.regions) == 1
    [region] = packaging.regions
    assert (region.x, region.y) == (far - REGION_PAD, COLUMN_TOP - REGION_PAD)
    assert (region.width, region.height) == (
        card.width + 2 * REGION_PAD,
        card.height + 2 * REGION_PAD,
    )


def test_shared_suppliers_name_a_card_feeding_several_stages() -> None:
    assert shared_suppliers(copper()) == [SharedSupplier(code="sen", processes=5, stages=3)]


def test_shared_suppliers_count_the_stages_their_consumers_hold_not_the_span() -> None:
    drawn = water_chain()
    for code in ("drinking_water", "pet_bottle"):
        next(p for p in drawn.processes if p.code == code).exchanges.append(
            Exchange(
                id=uuid.uuid4(),
                type="product",
                name="grid",
                amount=1.0,
                unit="kWh",
                input=ForegroundRef(code="grid"),
            )
        )
    drawn.processes.append(process("grid"))
    # use and packaging sit at the two ends of stage_order, three stages apart
    assert stage_order(drawn) == [
        "use",
        "distribution and end of life",
        "distribution",
        "production",
        "packaging",
    ]
    assert shared_suppliers(drawn) == [SharedSupplier(code="grid", processes=2, stages=2)]


def staged_chain() -> ProductSystem:
    """A functional unit whose stage feeds nothing, the smelting stage it takes from, the
    extraction stage below that and the energy stage every one of them takes electricity from."""
    return system(
        tagged(process("refinery", ["smelter", "grid"]), "refining"),
        tagged(process("smelter", ["mine", "grid"]), "smelting"),
        tagged(process("mine", ["grid"]), "extraction"),
        tagged(process("grid"), "energy"),
    )


def test_a_stage_band_is_the_next_stage_with_the_fewest_arrows_into_the_rest() -> None:
    drawn = copper()
    placed = {p.code: p for p in arrange(drawn, ["refinery"], {}, emitted(drawn))}
    # sen feeds every stage and sits leftmost; each stage is right of the one it feeds
    assert placed["sen"].x < placed["mine"].x < placed["concentrator"].x < placed["transport"].x
    assert placed["transport"].x < placed["smelter"].x < placed["refinery"].x


def test_a_staged_dag_whose_unit_stage_feeds_nothing_has_no_backward_arrow() -> None:
    drawn = staged_chain()
    placed = arrange(drawn, ["refinery"], {}, emitted(drawn))
    stages = card_stages(drawn)
    spots = {p.code: p for p in placed}
    backwards = [
        (arrow.provider, arrow.consumer)
        for arrow in routed(placed, links(drawn), link_texts(drawn, None))
        if arrow.provider != arrow.consumer
        and stages[arrow.provider] is not None
        and stages[arrow.consumer] is not None
        and spots[arrow.consumer].x <= spots[arrow.provider].x
    ]
    assert backwards == []
    assert spots["grid"].x < spots["mine"].x < spots["smelter"].x < spots["refinery"].x


def test_a_released_staged_nine_has_no_backward_arrow_no_shared_end_and_scores_below_23() -> None:
    drawn = staged_nine()
    placed = arrange(drawn, anchors(drawn), {}, emitted(drawn))
    found = routed(placed, links(drawn), link_texts(drawn, None))
    assert [t for t in troubles(placed, found) if t.kind == "edge_backwards"] == []
    ends: dict[tuple[float, float], int] = {}
    for arrow in found:
        ends[arrow.points[-1]] = ends.get(arrow.points[-1], 0) + 1
    assert [point for point, count in ends.items() if count > 1] == []
    assert score(troubles(placed, found)) < 23


def test_the_two_searches_measure_no_more_drawings_than_the_budget_allows() -> None:
    drawn = hundred()
    arrows = len(links(drawn))
    spent = layout_module.Evaluations(limit=layout_module.evaluation_budget(arrows))
    arrange(drawn, anchors(drawn), {}, emitted(drawn), budget=spent)
    assert spent.limit == 400_000 // arrows**2
    assert spent.used == spent.limit


def test_a_small_drawing_stops_spending_its_budget_once_no_swap_lowers_it() -> None:
    drawn = system(process("fu", ["a", "b"]), process("a"), process("b"))
    spent = layout_module.Evaluations(limit=layout_module.evaluation_budget(len(links(drawn))))
    arrange(drawn, ["fu"], {}, emitted(drawn), budget=spent)
    assert 0 < spent.used < spent.limit


def test_a_cycle_is_arranged_within_its_budget() -> None:
    drawn = system(process("fu", ["a"]), process("a", ["fu"]), process("b", ["a"]))
    spent = layout_module.Evaluations(limit=layout_module.evaluation_budget(len(links(drawn))))
    placed = arrange(drawn, ["fu"], {}, emitted(drawn), budget=spent)
    assert sorted(p.code for p in placed) == ["a", "b", "fu"]
    assert spent.used <= spent.limit


def test_a_drawing_with_no_arrow_places_every_card_apart() -> None:
    drawn = system(process("a"), process("b"), process("c"))
    spent = layout_module.Evaluations(limit=layout_module.evaluation_budget(0))
    placed = arrange(drawn, [], {}, emitted(drawn), budget=spent)
    assert sorted(p.code for p in placed) == ["a", "b", "c"]
    assert overlapping(placed) == []
    assert spent.used <= spent.limit


def test_neither_search_moves_a_held_card() -> None:
    drawn = staged_nine()
    held = {"concentrator": (1234.0, 567.0), "grid": (0.0, 0.0)}
    placed = {p.code: p for p in arrange(drawn, anchors(drawn), held, emitted(drawn))}
    assert (placed["concentrator"].x, placed["concentrator"].y) == (1234.0, 567.0)
    assert (placed["grid"].x, placed["grid"].y) == (0.0, 0.0)
    assert placed["concentrator"].held and placed["grid"].held
    assert overlapping(list(placed.values())) == []


def test_two_reads_of_one_drawing_answer_the_same_positions() -> None:
    drawn = staged_nine()
    first = arrange(drawn, anchors(drawn), {}, emitted(drawn))
    second = arrange(drawn, anchors(drawn), {}, emitted(drawn))
    assert [(p.code, p.x, p.y) for p in first] == [(p.code, p.x, p.y) for p in second]


def test_the_height_pass_leaves_the_reference_at_the_middle_height() -> None:
    drawn = staged_nine()
    placed = {p.code: p for p in arrange(drawn, anchors(drawn), {}, emitted(drawn))}
    others = [p for p in placed.values() if p.code != "refinery"]
    middle = (min(p.y for p in others) + max(p.y + p.height for p in others)) / 2
    assert abs(placed["refinery"].y + placed["refinery"].height / 2 - middle) < 1.0
