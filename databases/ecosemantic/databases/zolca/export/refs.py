"""openLCA's references, `JsonRefs.asRef`: what a reference carries follows from its target's model.

A reference is `@type`, `@id` and `name` of the *target row*, with `category` when the target's
`F_CATEGORY` resolves to a path. A flow adds `flowType`, `refUnit` and its location's `CODE`; a
process adds `processType`, the `flowType` of its quantitative-reference flow and its location's
`CODE`; a flow property and an impact category add `refUnit`; a `Unit` carries nothing else
(`JsonRefs.java:59-145`).
"""

from __future__ import annotations

from ecosemantic.databases.zolca.export import render
from ecosemantic.databases.zolca.export.tables import Tables, foreign
from ecosemantic.errors import NotSupported

MODEL_TABLES = {
    "Actor": "TBL_ACTORS",
    "Category": "TBL_CATEGORIES",
    "Currency": "TBL_CURRENCIES",
    "DQSystem": "TBL_DQ_SYSTEMS",
    "Flow": "TBL_FLOWS",
    "FlowProperty": "TBL_FLOW_PROPERTIES",
    "ImpactCategory": "TBL_IMPACT_CATEGORIES",
    "ImpactMethod": "TBL_IMPACT_METHODS",
    "Location": "TBL_LOCATIONS",
    "NwSet": "TBL_NW_SETS",
    "Parameter": "TBL_PARAMETERS",
    "Process": "TBL_PROCESSES",
    "Source": "TBL_SOURCES",
    "Unit": "TBL_UNITS",
    "UnitGroup": "TBL_UNIT_GROUPS",
}


def ref(tables: Tables, model: str, row_id: int) -> dict[str, object]:
    """`JsonRefs.asRef`: the reference openLCA writes for the row `model` names.

    `location` is the target's location's `CODE`, a string, on a flow's and on a process's reference
    alike; a process's *record* writes its own location as a reference, which `entities` does.
    """
    row = _row(tables=tables, model=model, row_id=row_id)
    found: dict[str, object] = {"@type": model, "@id": row["REF_ID"], "name": row["NAME"]}
    if model != "Unit":
        category = render.category_path(tables, foreign(row, "F_CATEGORY"))
        if category is not None:
            found["category"] = category
    match model:
        case "Flow":
            found["flowType"] = row["FLOW_TYPE"]
            unit = _reference_unit(tables, _key(row, "F_REFERENCE_FLOW_PROPERTY"))
            if unit is not None:
                found["refUnit"] = unit
            location = foreign(row, "F_LOCATION")
            if location is not None:
                found["location"] = str(tables.row("TBL_LOCATIONS", location)["CODE"])
        case "Process":
            found["processType"] = row["PROCESS_TYPE"]
            reference = _key(row, "F_QUANTITATIVE_REFERENCE")
            found["flowType"] = _quantitative_flow_type(tables, reference)
            location = foreign(row, "F_LOCATION")
            if location is not None:
                found["location"] = str(tables.row("TBL_LOCATIONS", location)["CODE"])
        case "FlowProperty":
            unit = _reference_unit(tables, row_id)
            if unit is not None:
                found["refUnit"] = unit
        case "ImpactCategory":
            found["refUnit"] = row["REFERENCE_UNIT"]
    return found


def _row(*, tables: Tables, model: str, row_id: int) -> dict[str, object]:
    """The target row a reference of `model` is built from."""
    table = MODEL_TABLES.get(model)
    if table is None:
        raise NotSupported(f"{model} is no openLCA entity a reference is written to")
    return tables.row(table, row_id)


def _reference_unit(tables: Tables, flow_property_id: int) -> str | None:
    """`JsonRefs.unitOf`: the name of a flow property's unit group's reference unit."""
    property_row = tables.row("TBL_FLOW_PROPERTIES", flow_property_id)
    unit_group = foreign(property_row, "F_UNIT_GROUP")
    if unit_group is None:
        return None
    group = tables.row("TBL_UNIT_GROUPS", unit_group)
    return str(tables.row("TBL_UNITS", _key(group, "F_REFERENCE_UNIT"))["NAME"])


def _quantitative_flow_type(tables: Tables, exchange_id: int) -> str:
    """`JsonRefs.flowTypeOf`: the `FLOW_TYPE` of the flow a quantitative reference names."""
    exchange = tables.row("TBL_EXCHANGES", exchange_id)
    flow = tables.row("TBL_FLOWS", _key(exchange, "F_FLOW"))
    return str(flow["FLOW_TYPE"])


def _key(row: dict[str, object], column: str) -> int:
    """A foreign key a reference must follow to name what it points at."""
    found = foreign(row, column)
    if found is None:
        raise NotSupported(f"{column} names no row a reference follows")
    return found
