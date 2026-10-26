from __future__ import annotations

import pytest

from ecosemantic.errors import NotSupported
from ecosemantic.model import units
from ecosemantic.model.units import UNITS, by_name, by_symbol, canonical, convert


def test_names_and_symbols_are_unique() -> None:
    names = [u.name for u in UNITS]
    symbols = [s for u in UNITS for s in u.symbols]
    assert len(names) == len(set(names)) and len(symbols) == len(set(symbols))


def test_every_group_has_one_canonical_unit() -> None:
    for group in {u.group for u in UNITS}:
        unit = canonical(group)
        assert unit.factor == 1.0 and unit.group == group


def test_lookups_answer_the_writer_and_the_importer() -> None:
    assert by_name("kilogram").symbols[0] == "kg"
    assert by_symbol("g").name == "gram" and by_symbol("g").factor == 0.001
    assert by_symbol("kWh").group == by_name("megajoule").group
    assert by_symbol("m²") is by_symbol("m2")
    assert by_symbol("Item(s)").name == "unit"


def test_convert_scales_to_the_canonical_unit() -> None:
    assert convert(500.0, by_symbol("g")) == pytest.approx(0.5)
    assert convert(2.0, by_symbol("kWh")) == pytest.approx(7.2)
    assert convert(3.0, by_symbol("kg*km")) == pytest.approx(0.003)
    assert convert(1.0, by_symbol("Bq")) == pytest.approx(0.001)


def test_the_writer_names_are_all_in_the_table() -> None:
    for name in (
        "kilogram",
        "kilowatt hour",
        "unit",
        "cubic meter",
        "megajoule",
        "hectare",
        "ton kilometer",
        "square meter",
        "hour",
        "kilometer",
        "meter",
        "person kilometer",
        "litre",
        "meter-year",
        "square meter-year",
        "kilometer-year",
        "kilogram day",
        "kilo Becquerel",
        "cubic meter-year",
        "standard cubic meter",
        "normal cubic meter",
    ):
        by_name(name)


@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("metric ton*km", "ton kilometer"),
        ("m2*year", "square meter-year"),
        ("hour", "hour"),
        ("m*year", "meter-year"),
        ("m3*year", "cubic meter-year"),
        ("Sm3", "standard cubic meter"),
        ("Nm3", "normal cubic meter"),
        ("kg*day", "kilogram day"),
        ("person*km", "person kilometer"),
        ("km*year", "kilometer-year"),
    ],
)
def test_ecoinvent_spellings_name_the_units_the_core_knows(symbol: str, name: str) -> None:
    assert units.by_symbol(symbol).name == name


def test_normal_and_standard_cubic_metres_are_units_of_their_own() -> None:
    standard = units.by_symbol("Sm3")
    normal = units.by_symbol("Nm3")
    assert standard.name == "standard cubic meter"
    assert normal.name == "normal cubic meter"
    assert standard.symbols == ("Sm3", "Sm³") and normal.symbols == ("Nm3", "Nm³")
    assert standard.group == units.STANDARD_VOLUME
    assert normal.group == units.NORMAL_VOLUME
    assert units.canonical(units.STANDARD_VOLUME) == standard
    assert units.canonical(units.NORMAL_VOLUME) == normal


def test_unknown_units_are_not_supported() -> None:
    with pytest.raises(NotSupported, match="furlong"):
        by_name("furlong")
    with pytest.raises(NotSupported, match="fur"):
        by_symbol("fur")
    with pytest.raises(NotSupported):
        canonical("Units of taste")


def test_currency_and_guest_nights_are_units_of_their_own() -> None:
    # ecoinvent 3.12 carries 11 hotel datasets in guest nights and 5 economic flows in EUR2005
    night = units.by_name("guest night")
    assert units.by_symbol("guest night") == night and night.group == units.GUEST_NIGHTS
    assert units.canonical(units.CURRENCY) == units.by_symbol("EUR2005")


@pytest.mark.parametrize(
    ("unit", "written"),
    [
        ("kilogram", "kg"),
        ("kilowatt hour", "kWh"),
        ("cubic meter", "m3"),
        ("megajoule", "MJ"),
        ("ton kilometer", "tkm"),
        ("unit", "unit"),
        ("Item(s)", "unit"),
        ("square meter-year", "m2a"),
        ("kg", "kg"),
        ("piece", "piece"),
    ],
)
def test_a_unit_is_written_as_its_shortest_symbol(unit: str, written: str) -> None:
    assert units.symbol(unit) == written


def test_openlca_spells_the_pound_and_the_cubic_foot_with_an_ordinary_space() -> None:
    assert units.by_symbol("lb av") == units.by_symbol("lb\xa0av") == units.by_name("pound")
    assert units.by_symbol("cu ft") == units.by_symbol("cu\xa0ft") == units.by_name("cubic foot")


def test_the_us_customary_units_uslci_uses_have_their_defined_factors() -> None:
    assert (units.by_symbol("sh tn").group, units.by_symbol("sh tn").factor) == (
        units.MASS,
        907.18474,
    )
    for symbol in ("gal (US liq)", "gal (US fl)"):
        assert units.by_symbol(symbol).group == units.VOLUME
        assert units.by_symbol(symbol).factor == pytest.approx(0.003785411784)
    assert units.by_symbol("gal (Imp)").factor == pytest.approx(0.00454609)
    assert (units.by_symbol("t*mi").group, units.by_symbol("t*mi").factor) == (
        units.MASS_LENGTH,
        1.609344,
    )


def test_the_us_dollar_is_a_currency_of_its_own() -> None:
    # a group of its own is what keeps a factor of 1 from turning dollars into EUR2005
    dollar = units.by_symbol("USD")
    assert dollar.group == units.US_DOLLARS and units.canonical(units.US_DOLLARS) == dollar
    assert units.canonical(units.CURRENCY) == units.by_symbol("EUR2005")
    assert dollar.group != units.by_symbol("EUR2005").group
