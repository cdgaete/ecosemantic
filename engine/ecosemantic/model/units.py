"""The units the core knows: their long names, openLCA's symbols, and physical factors."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ecosemantic.errors import NotSupported

MASS = "Units of mass"
ENERGY = "Units of energy"
VOLUME = "Units of volume"
STANDARD_VOLUME = "Units of standard volume"
NORMAL_VOLUME = "Units of normal volume"
AREA = "Units of area"
LENGTH = "Units of length"
TIME = "Units of time"
ITEMS = "Units of items"
RADIOACTIVITY = "Units of radioactivity"
MASS_LENGTH = "Units of mass*length"
MASS_TIME = "Units of mass*time"
AREA_TIME = "Units of area*time"
LENGTH_TIME = "Units of length*time"
VOLUME_TIME = "Units of volume*time"
PERSON_TRANSPORT = "Units of person transport"
VEHICLE_TRANSPORT = "Units of vehicle transport"
CURRENCY = "Units of currency"
US_DOLLARS = "Units of US dollars"
GUEST_NIGHTS = "Units of guest nights"


class Unit(BaseModel):
    """One unit: its long name, the symbols openLCA writes it as, its group, its factor."""

    model_config = ConfigDict(frozen=True)

    name: str
    symbols: tuple[str, ...]
    group: str
    factor: float


def _unit(name: str, symbols: str, group: str, factor: float) -> Unit:
    return Unit(name=name, symbols=tuple(symbols.split(" ")), group=group, factor=factor)


UNITS: tuple[Unit, ...] = (
    _unit("kilogram", "kg", MASS, 1.0),
    _unit("gram", "g", MASS, 1e-3),
    _unit("milligram", "mg", MASS, 1e-6),
    _unit("microgram", "µg ug", MASS, 1e-9),
    _unit("ton", "t Mg", MASS, 1e3),
    _unit("kiloton", "kt", MASS, 1e6),
    Unit(name="short ton", symbols=("sh tn",), group=MASS, factor=907.18474),
    Unit(
        name="pound",
        symbols=("lb", "lb\xa0av", "lb av"),
        group=MASS,
        factor=0.45359237,
    ),
    _unit("ounce", "oz oz av", MASS, 0.028349523125),
    _unit("megajoule", "MJ", ENERGY, 1.0),
    _unit("kilowatt hour", "kWh", ENERGY, 3.6),
    _unit("joule", "J", ENERGY, 1e-6),
    _unit("kilojoule", "kJ", ENERGY, 1e-3),
    _unit("gigajoule", "GJ", ENERGY, 1e3),
    _unit("terajoule", "TJ", ENERGY, 1e6),
    _unit("petajoule", "PJ", ENERGY, 1e9),
    _unit("watt hour", "Wh", ENERGY, 3.6e-3),
    _unit("megawatt hour", "MWh", ENERGY, 3.6e3),
    _unit("British thermal unit", "btu", ENERGY, 1.05505585262e-3),
    _unit("kilocalorie", "kcal", ENERGY, 4.1868e-3),
    _unit("cubic meter", "m3 m³", VOLUME, 1.0),
    _unit("litre", "l", VOLUME, 1e-3),
    _unit("millilitre", "ml mL", VOLUME, 1e-6),
    _unit("cubic centimeter", "cm3", VOLUME, 1e-6),
    _unit("cubic decimeter", "dm3", VOLUME, 1e-3),
    Unit(
        name="cubic foot",
        symbols=("cu\xa0ft", "cuft", "cu ft"),
        group=VOLUME,
        factor=0.028316846592,
    ),
    Unit(
        name="US liquid gallon",
        symbols=("gal (US liq)", "gal (US fl)"),
        group=VOLUME,
        factor=0.003785411784,
    ),
    Unit(name="imperial gallon", symbols=("gal (Imp)",), group=VOLUME, factor=0.00454609),
    _unit("standard cubic meter", "Sm3 Sm³", STANDARD_VOLUME, 1.0),
    _unit("normal cubic meter", "Nm3 Nm³", NORMAL_VOLUME, 1.0),
    _unit("square meter", "m2 m²", AREA, 1.0),
    _unit("hectare", "ha", AREA, 1e4),
    _unit("square kilometer", "km2 km²", AREA, 1e6),
    _unit("square centimeter", "cm2", AREA, 1e-4),
    _unit("square foot", "ft2 ft²", AREA, 0.09290304),
    _unit("meter", "m", LENGTH, 1.0),
    _unit("kilometer", "km", LENGTH, 1e3),
    _unit("centimeter", "cm", LENGTH, 1e-2),
    _unit("millimeter", "mm", LENGTH, 1e-3),
    _unit("mile", "mile mi", LENGTH, 1609.344),
    _unit("foot", "ft", LENGTH, 0.3048),
    _unit("inch", "in inch", LENGTH, 0.0254),
    _unit("hour", "h hr hour", TIME, 1.0),
    _unit("day", "d day", TIME, 24.0),
    _unit("minute", "min", TIME, 1 / 60),
    _unit("second", "s", TIME, 1 / 3600),
    _unit("year", "a year yr", TIME, 8760.0),
    _unit("unit", "Item(s) unit", ITEMS, 1.0),
    _unit("dozen", "Dozen(s)", ITEMS, 12.0),
    _unit("kilo Becquerel", "kBq", RADIOACTIVITY, 1.0),
    _unit("becquerel", "Bq", RADIOACTIVITY, 1e-3),
    _unit("millibecquerel", "mBq", RADIOACTIVITY, 1e-6),
    _unit("curie", "Ci", RADIOACTIVITY, 3.7e7),
    Unit(
        name="ton kilometer",
        symbols=("t*km", "tkm", "metric ton*km"),
        group=MASS_LENGTH,
        factor=1.0,
    ),
    _unit("kilogram kilometer", "kg*km kgkm", MASS_LENGTH, 1e-3),
    _unit("kiloton kilometer", "kt*km ktkm", MASS_LENGTH, 1e3),
    Unit(name="ton mile", symbols=("t*mi",), group=MASS_LENGTH, factor=1.609344),
    _unit("kilogram day", "kg*d kg*day", MASS_TIME, 1.0),
    _unit("kilogram year", "kg*a kgy", MASS_TIME, 365.0),
    _unit("ton day", "t*d", MASS_TIME, 1e3),
    _unit("ton year", "t*a", MASS_TIME, 365e3),
    _unit("square meter-year", "m2*a m²*a m2a m²a m2*year", AREA_TIME, 1.0),
    _unit("square meter-day", "m2*d", AREA_TIME, 1 / 365),
    _unit("hectare-year", "ha*a ha a", AREA_TIME, 1e4),
    _unit("square kilometer-year", "km2*a km²*a km2a km²a", AREA_TIME, 1e6),
    _unit("meter-year", "m*a my ma m*year", LENGTH_TIME, 1.0),
    _unit("kilometer-year", "km*a kmy km*year", LENGTH_TIME, 1e3),
    _unit("cubic meter-year", "m3*a m³*a m3a m3y m3*year", VOLUME_TIME, 1.0),
    _unit("cubic meter-day", "m3*d m³*d m3d m3day", VOLUME_TIME, 1 / 365),
    _unit("litre-year", "l*a", VOLUME_TIME, 1e-3),
    _unit("person kilometer", "p*km pkm personkm person*km", PERSON_TRANSPORT, 1.0),
    _unit("vehicle kilometer", "v*km vkm", VEHICLE_TRANSPORT, 1.0),
    _unit("EUR2005", "EUR2005", CURRENCY, 1.0),
    _unit("US dollar", "USD", US_DOLLARS, 1.0),
    Unit(name="guest night", symbols=("guest night",), group=GUEST_NIGHTS, factor=1.0),
)

_BY_NAME: dict[str, Unit] = {u.name: u for u in UNITS}
_BY_SYMBOL: dict[str, Unit] = {s: u for u in UNITS for s in u.symbols}
_CANONICAL: dict[str, Unit] = {u.group: u for u in UNITS if u.factor == 1.0}


def by_name(name: str) -> Unit:
    """The unit with this long name."""
    if name not in _BY_NAME:
        raise NotSupported(f"unit {name!r} is not one the core knows")
    return _BY_NAME[name]


def by_symbol(symbol: str) -> Unit:
    """The unit openLCA writes with this symbol."""
    if symbol not in _BY_SYMBOL:
        raise NotSupported(f"unit symbol {symbol!r} is not one the core knows")
    return _BY_SYMBOL[symbol]


def symbol(unit: str) -> str:
    """The shortest symbol of the unit a long name or a symbol names, the first of equal length
    in the table's order; a unit the table does not hold is written as given."""
    known = _BY_NAME.get(unit) or _BY_SYMBOL.get(unit)
    if known is None:
        return unit
    return min(known.symbols, key=len)


def canonical(group: str) -> Unit:
    """The unit a group's amounts are stored in."""
    if group not in _CANONICAL:
        raise NotSupported(f"unit group {group!r} is not one the core knows")
    return _CANONICAL[group]


def convert(amount: float, unit: Unit) -> float:
    """The amount in the unit's group's canonical unit."""
    return amount * unit.factor
