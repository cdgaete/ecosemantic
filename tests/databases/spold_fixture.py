"""A synthetic ecoinvent release: MasterData, EcoSpold2 datasets, three workbooks and the
matrix export the build's numbers are compared with."""

from __future__ import annotations

import csv
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xlsxwriter
from python_calamine import CalamineWorkbook

from ecosemantic.databases.ecoinvent.release import Release

NS = "http://www.EcoInvent.org/EcoSpold02"
ET.register_namespace("", NS)
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

STEEL_ACTIVITY = "00000001-0000-4000-8000-000000000001"
STEEL_PRODUCT = "00000002-0000-4000-8000-000000000002"
ELEC_ACTIVITY = "00000003-0000-4000-8000-000000000003"
ELEC_PRODUCT = "00000004-0000-4000-8000-000000000004"
TREAT_ACTIVITY = "00000005-0000-4000-8000-000000000005"
TREAT_PRODUCT = "00000006-0000-4000-8000-000000000006"
CO2 = "00000007-0000-4000-8000-000000000007"
IRON = "00000008-0000-4000-8000-000000000008"
KILOGRAM = "00000009-0000-4000-8000-000000000009"
KILOWATT_HOUR = "0000000a-0000-4000-8000-00000000000a"
UNUSED = "0000000d-0000-4000-8000-00000000000d"
_AIR_SUBCOMPARTMENT = "0000000b-0000-4000-8000-00000000000b"
_GROUND_SUBCOMPARTMENT = "0000000c-0000-4000-8000-00000000000c"
_STEEL_REFERENCE = "00000010-0000-4000-8000-000000000010"
_STEEL_ELECTRICITY = "00000011-0000-4000-8000-000000000011"
_STEEL_IRON = "00000012-0000-4000-8000-000000000012"
_STEEL_CO2 = "00000013-0000-4000-8000-000000000013"
_STEEL_WASTE = "00000014-0000-4000-8000-000000000014"
_ELEC_REFERENCE = "00000015-0000-4000-8000-000000000015"
_ELEC_CO2 = "00000016-0000-4000-8000-000000000016"
_ELEC_IRON = "00000020-0000-4000-8000-000000000020"
_TREAT_REFERENCE = "00000017-0000-4000-8000-000000000017"
_TREAT_ELECTRICITY = "00000018-0000-4000-8000-000000000018"
_TREAT_CO2 = "00000019-0000-4000-8000-000000000019"
AIR_ACTIVITY = "0000001a-0000-4000-8000-00000000001a"
AIR_PRODUCT = "0000001b-0000-4000-8000-00000000001b"
_AIR_REFERENCE = "0000001c-0000-4000-8000-00000000001c"
_AIR_ELECTRICITY = "0000001d-0000-4000-8000-00000000001d"
_AIR_SELF = "0000001e-0000-4000-8000-00000000001e"
_AIR_CO2 = "0000001f-0000-4000-8000-00000000001f"

STEEL = f"{STEEL_ACTIVITY}_{STEEL_PRODUCT}"
ELEC = f"{ELEC_ACTIVITY}_{ELEC_PRODUCT}"
TREAT = f"{TREAT_ACTIVITY}_{TREAT_PRODUCT}"
AIR = f"{AIR_ACTIVITY}_{AIR_PRODUCT}"

ECOQUERY_INDEX: dict[str, int] = {STEEL: 10001, ELEC: 10002, TREAT: 10003, AIR: 10004}

METHOD = "IPCC 2021"
CATEGORY = "climate change"
INDICATOR = "GWP100"
INDICATOR_UNIT = "kg CO2-Eq"

FACTOR_COLUMNS = ("Method", "Category", "Indicator", "Name", "Compartment", "Subcompartment", "CF")
INDICATOR_COLUMNS = ("Method", "Category", "Indicator", "Indicator Unit")
INDEX_COLUMNS = {
    "ie": ("activityName", "geography", "product", "unitName", "index"),
    "ee": ("name", "compartment", "subcompartment", "unitName", "index"),
    "lcia": ("method", "category", "indicator", "unitName", "index"),
}
MATRIX_COLUMNS = (
    "row",
    "column",
    "coefficient",
    "uncertainty type",
    "varianceWithPedigreeUncertainty",
    "minValue",
    "mostLikelyValue",
    "maxValue",
)
OVERVIEW_COLUMNS = (
    "Activity UUID & Product UUID",
    "Activity UUID",
    "ecoQuery URL",
    "Activity Name",
    "Geography",
)

_ELEMENTARY = (
    (CO2, "Carbon dioxide, fossil", "air", "unspecified", _AIR_SUBCOMPARTMENT, "000124-38-9"),
    (IRON, "Iron", "natural resource", "in ground", _GROUND_SUBCOMPARTMENT, "007439-89-6"),
)
_UNUSED = (UNUSED, "Argon", "air", "unspecified", _AIR_SUBCOMPARTMENT, "007440-37-1")
_DECLARED = (*_ELEMENTARY, _UNUSED)
UNUSED_FACTOR = 3.0
_CANCEL_FACTOR = -1.0
UNITS = ("kg", "kWh", "hogshead")

_DEFAULTS: dict[str, object] = {
    "steel_unit": "kg",
    "steel_geography": "NA",
    "lognormal_variance": 0.04,
    "extra_factor_row": False,
    "extra_category": False,
    "cancelling_factor": False,
    "overview_missing": False,
}


@dataclass(frozen=True)
class _Flow:
    """One exchange of an EcoSpold2 dataset, keyed to its MasterData flow by ``masterdata``."""

    id: str
    masterdata: str
    name: str
    unit: str
    unit_id: str
    amount: float
    group: int
    output: bool
    elementary: bool = False
    link: str | None = None
    variance: float | None = None


@dataclass(frozen=True)
class _Dataset:
    """One synthetic dataset: its native id, its activity, and the exchanges it declares."""

    native: str
    activity: str
    name: str
    geography: str
    flows: tuple[_Flow, ...]


def _steel_flows(steel_unit: str, variance: float) -> tuple[_Flow, ...]:
    return (
        _Flow(
            id=_STEEL_REFERENCE,
            masterdata=STEEL_PRODUCT,
            name="steel",
            unit=steel_unit,
            unit_id=KILOGRAM,
            amount=1.0,
            group=0,
            output=True,
        ),
        _Flow(
            id=_STEEL_ELECTRICITY,
            masterdata=ELEC_PRODUCT,
            name="electricity",
            unit="kWh",
            unit_id=KILOWATT_HOUR,
            amount=2.0,
            group=5,
            output=False,
            link=ELEC_ACTIVITY,
            variance=variance,
        ),
        _Flow(
            id=_STEEL_IRON,
            masterdata=IRON,
            name="Iron",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.5,
            group=4,
            output=False,
            elementary=True,
        ),
        _Flow(
            id=_STEEL_CO2,
            masterdata=CO2,
            name="Carbon dioxide, fossil",
            unit="kg",
            unit_id=KILOGRAM,
            amount=1.5,
            group=4,
            output=True,
            elementary=True,
        ),
        _Flow(
            id=_STEEL_WASTE,
            masterdata=TREAT_PRODUCT,
            name="waste plastic",
            unit="kg",
            unit_id=KILOGRAM,
            amount=-0.2,
            group=5,
            output=False,
            link=TREAT_ACTIVITY,
        ),
    )


def _elec_flows(cancelling: bool) -> tuple[_Flow, ...]:
    flows = (
        _Flow(
            id=_ELEC_REFERENCE,
            masterdata=ELEC_PRODUCT,
            name="electricity",
            unit="kWh",
            unit_id=KILOWATT_HOUR,
            amount=1.0,
            group=0,
            output=True,
        ),
        _Flow(
            id=_ELEC_CO2,
            masterdata=CO2,
            name="Carbon dioxide, fossil",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.5,
            group=4,
            output=True,
            elementary=True,
        ),
    )
    if not cancelling:
        return flows
    return (
        *flows,
        _Flow(
            id=_ELEC_IRON,
            masterdata=IRON,
            name="Iron",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.5,
            group=4,
            output=False,
            elementary=True,
        ),
    )


def _treat_flows() -> tuple[_Flow, ...]:
    return (
        _Flow(
            id=_TREAT_REFERENCE,
            masterdata=TREAT_PRODUCT,
            name="waste plastic",
            unit="kg",
            unit_id=KILOGRAM,
            amount=-1.0,
            group=0,
            output=True,
        ),
        _Flow(
            id=_TREAT_ELECTRICITY,
            masterdata=ELEC_PRODUCT,
            name="electricity",
            unit="kWh",
            unit_id=KILOWATT_HOUR,
            amount=0.1,
            group=5,
            output=False,
            link=ELEC_ACTIVITY,
        ),
        _Flow(
            id=_TREAT_CO2,
            masterdata=CO2,
            name="Carbon dioxide, fossil",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.3,
            group=4,
            output=True,
            elementary=True,
        ),
    )


def _air_flows() -> tuple[_Flow, ...]:
    return (
        _Flow(
            id=_AIR_REFERENCE,
            masterdata=AIR_PRODUCT,
            name="compressed air",
            unit="kg",
            unit_id=KILOGRAM,
            amount=1.0,
            group=0,
            output=True,
        ),
        _Flow(
            id=_AIR_ELECTRICITY,
            masterdata=ELEC_PRODUCT,
            name="electricity",
            unit="kWh",
            unit_id=KILOWATT_HOUR,
            amount=1.0,
            group=5,
            output=False,
            link=ELEC_ACTIVITY,
        ),
        _Flow(
            id=_AIR_SELF,
            masterdata=AIR_PRODUCT,
            name="compressed air",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.1,
            group=5,
            output=False,
            link=AIR_ACTIVITY,
        ),
        _Flow(
            id=_AIR_CO2,
            masterdata=CO2,
            name="Carbon dioxide, fossil",
            unit="kg",
            unit_id=KILOGRAM,
            amount=0.2,
            group=4,
            output=True,
            elementary=True,
        ),
    )


def build_release(root: Path, **overrides: object) -> Release:
    """Write a synthetic 3.10 cutoff release under ``root`` and return its Release."""
    unknown = sorted(set(overrides) - set(_DEFAULTS))
    if unknown:
        raise ValueError(f"unknown overrides: {unknown}")
    settings = {**_DEFAULTS, **overrides}
    steel_unit = str(settings["steel_unit"])
    steel_geography = str(settings["steel_geography"])
    variance = float(settings["lognormal_variance"])
    extra_factor_row = bool(settings["extra_factor_row"])
    extra_category = bool(settings["extra_category"])
    cancelling_factor = bool(settings["cancelling_factor"])
    overview_missing = bool(settings["overview_missing"])

    root.mkdir(parents=True, exist_ok=True)

    ecospold = root / "ecospold"
    _write_elementary_masterdata(ecospold / "MasterData" / "ElementaryExchanges.xml")
    _write_intermediate_masterdata(
        ecospold / "MasterData" / "IntermediateExchanges.xml", steel_unit
    )
    _write_units(ecospold / "MasterData" / "Units.xml")
    catalogue = (
        _Dataset(
            STEEL,
            STEEL_ACTIVITY,
            "steel production",
            steel_geography,
            _steel_flows(steel_unit, variance),
        ),
        _Dataset(
            ELEC, ELEC_ACTIVITY, "electricity production", "GLO", _elec_flows(cancelling_factor)
        ),
        _Dataset(TREAT, TREAT_ACTIVITY, "waste plastic treatment", "NA", _treat_flows()),
        _Dataset(AIR, AIR_ACTIVITY, "compressed air production", "GLO", _air_flows()),
    )
    datasets = ecospold / "datasets"
    for dataset in catalogue:
        _write_dataset(
            datasets / f"{dataset.native}.spold",
            dataset.activity,
            dataset.name,
            dataset.geography,
            dataset.flows,
        )

    lcia = root / "lcia.xlsx"
    _write_lcia(lcia, extra_factor_row, extra_category, cancelling_factor)

    matrix = root / "matrix"
    matrices = _matrices(catalogue, cancelling_factor)
    _write_matrix(matrix, catalogue, matrices)

    cumulative_lcia = root / "cumulative.xlsx"
    _write_cumulative(cumulative_lcia, catalogue, matrices)

    overview = root / "overview.xlsx"
    _write_overview(overview, steel_geography, overview_missing)

    return Release(
        version="3.10",
        system_model="cutoff",
        ecospold=ecospold,
        lcia=lcia,
        matrix=matrix,
        cumulative_lcia=cumulative_lcia,
        overview=overview,
    )


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attributes: str) -> ET.Element:
    child = ET.SubElement(parent, f"{{{NS}}}{tag}", attributes)
    if text is not None:
        child.text = text
    return child


def _localised(parent: ET.Element, tag: str, text: str) -> ET.Element:
    return _sub(parent, tag, text, **{_XML_LANG: "en"})


def _number(value: float) -> str:
    return repr(value)


def _write_xml(path: Path, root: ET.Element) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_elementary_masterdata(path: Path) -> None:
    root = ET.Element(f"{{{NS}}}validElementaryExchanges")
    for flow_id, name, compartment, subcompartment, subcompartment_id, cas in _DECLARED:
        exchange = ET.SubElement(
            root,
            f"{{{NS}}}elementaryExchange",
            {"id": flow_id, "unitId": KILOGRAM, "casNumber": cas},
        )
        _localised(exchange, "name", name)
        _localised(exchange, "unitName", "kg")
        pair = _sub(exchange, "compartment", subcompartmentId=subcompartment_id)
        _localised(pair, "compartment", compartment)
        _localised(pair, "subcompartment", subcompartment)
    _write_xml(path, root)


def _write_intermediate_masterdata(path: Path, steel_unit: str) -> None:
    root = ET.Element(f"{{{NS}}}validIntermediateExchanges")
    products = (
        (STEEL_PRODUCT, "steel", steel_unit, KILOGRAM),
        (ELEC_PRODUCT, "electricity", "kWh", KILOWATT_HOUR),
        (TREAT_PRODUCT, "waste plastic", "kg", KILOGRAM),
        (AIR_PRODUCT, "compressed air", "kg", KILOGRAM),
    )
    for product, name, unit, unit_id in products:
        exchange = ET.SubElement(
            root, f"{{{NS}}}intermediateExchange", {"id": product, "unitId": unit_id}
        )
        _localised(exchange, "name", name)
        _localised(exchange, "unitName", unit)
    _write_xml(path, root)


def _write_units(path: Path) -> None:
    root = ET.Element(f"{{{NS}}}validUnits")
    for index, symbol in enumerate(UNITS):
        unit = ET.SubElement(
            root, f"{{{NS}}}unit", {"id": f"00000030-0000-4000-8000-0000000000{index:02d}"}
        )
        _localised(unit, "name", symbol)
    _write_xml(path, root)


def _write_dataset(
    path: Path, activity: str, name: str, geography: str, flows: tuple[_Flow, ...]
) -> None:
    root = ET.Element(f"{{{NS}}}ecoSpold")
    dataset = _sub(root, "childActivityDataset")
    description = _sub(dataset, "activityDescription")
    activity_element = _sub(description, "activity", id=activity)
    _localised(activity_element, "activityName", name)
    geography_element = _sub(description, "geography")
    _localised(geography_element, "shortname", geography)
    flow_data = _sub(dataset, "flowData")
    for flow in flows:
        _write_flow(flow_data, flow)
    _write_xml(path, root)


def _write_flow(flow_data: ET.Element, flow: _Flow) -> None:
    attributes = {"id": flow.id, "unitId": flow.unit_id, "amount": _number(flow.amount)}
    if flow.elementary:
        attributes["elementaryExchangeId"] = flow.masterdata
    else:
        attributes["intermediateExchangeId"] = flow.masterdata
        if flow.link is not None:
            attributes["activityLinkId"] = flow.link
    tag = "elementaryExchange" if flow.elementary else "intermediateExchange"
    element = ET.SubElement(flow_data, f"{{{NS}}}{tag}", attributes)
    _localised(element, "name", flow.name)
    _localised(element, "unitName", flow.unit)
    if flow.variance is not None:
        uncertainty = _sub(element, "uncertainty")
        _sub(
            uncertainty,
            "lognormal",
            meanValue=_number(flow.amount),
            mu=_number(math.log(flow.amount)),
            variance=_number(flow.variance),
            varianceWithPedigreeUncertainty=_number(flow.variance),
        )
    _sub(element, "outputGroup" if flow.output else "inputGroup", str(flow.group))


def _write_lcia(
    path: Path, extra_factor_row: bool, extra_category: bool, cancelling_factor: bool
) -> None:
    factors = [[METHOD, CATEGORY, INDICATOR, "Carbon dioxide, fossil", "air", "unspecified", 1.0]]
    indicators = [[METHOD, CATEGORY, INDICATOR, INDICATOR_UNIT]]
    if extra_category:
        factors.append(
            [METHOD, "water use", "WDP", "Carbon dioxide, fossil", "air", "unspecified", 2.0]
        )
        indicators.append([METHOD, "water use", "WDP", "m3"])
    if extra_factor_row:
        factors.append([METHOD, CATEGORY, INDICATOR, "Unobtainium", "air", "unspecified", 5.0])
    if cancelling_factor:
        factors.append(
            [METHOD, CATEGORY, INDICATOR, "Iron", "natural resource", "in ground", _CANCEL_FACTOR]
        )
    factors.append([METHOD, CATEGORY, INDICATOR, "Argon", "air", "unspecified", UNUSED_FACTOR])
    _write_workbook(
        path,
        {
            "CFs": [list(FACTOR_COLUMNS), *factors],
            "Indicators": [list(INDICATOR_COLUMNS), *indicators],
        },
    )


def _write_overview(path: Path, steel_geography: str, overview_missing: bool) -> None:
    rows: list[list[object]] = [
        [STEEL, STEEL_ACTIVITY, _ecoquery_url(STEEL), "steel production", steel_geography],
        [ELEC, ELEC_ACTIVITY, _ecoquery_url(ELEC), "electricity production", "GLO"],
        [TREAT, TREAT_ACTIVITY, _ecoquery_url(TREAT), "waste plastic treatment", "NA"],
        [AIR, AIR_ACTIVITY, _ecoquery_url(AIR), "compressed air production", "GLO"],
    ]
    if overview_missing:
        rows = [row for row in rows if row[0] != ELEC]
    _write_workbook(path, {"Cut-Off AO": [list(OVERVIEW_COLUMNS), *rows]})


def _ecoquery_url(native: str) -> str:
    return (
        f"https://ecoquery.ecoinvent.org/3.10/cutoff/dataset/{ECOQUERY_INDEX[native]}/documentation"
    )


def _reference(flows: tuple[_Flow, ...]) -> _Flow:
    return next(flow for flow in flows if not flow.elementary and flow.group == 0 and flow.output)


def _matrices(catalogue: tuple[_Dataset, ...], cancelling_factor: bool) -> dict[str, np.ndarray]:
    """A, B, C and every dataset's score for its reference amount, from the fixture's own
    exchanges and factors. Each column is folded as ecoinvent's export states it: scaled by the
    dataset's reference amount over its diagonal, so an activity's own consumption leaves the
    matrix."""
    count = len(catalogue)
    producers = {
        producer.masterdata: position
        for position, dataset in enumerate(catalogue)
        for producer in [_reference(dataset.flows)]
    }
    elementary = {flow_id: position for position, (flow_id, *_) in enumerate(_ELEMENTARY)}
    A = np.zeros((count, count))
    B = np.zeros((len(_ELEMENTARY), count))
    for column, dataset in enumerate(catalogue):
        for flow in dataset.flows:
            if flow.elementary:
                B[elementary[flow.masterdata], column] += flow.amount
            elif flow.group == 0 and flow.output:
                A[column, column] += flow.amount
            else:
                A[producers[flow.masterdata], column] -= flow.amount
    references = np.array([_reference(dataset.flows).amount for dataset in catalogue])
    diagonal = A.diagonal()
    factor = np.divide(references, diagonal, out=np.ones_like(references), where=diagonal != 0)
    A = A * factor
    B = B * factor
    C = np.zeros((1, len(_ELEMENTARY)))
    C[0, elementary[CO2]] = 1.0
    if cancelling_factor:
        C[0, elementary[IRON]] = _CANCEL_FACTOR
    scores = references[:, np.newaxis] * np.linalg.solve(A.T, (C @ B).T)
    return {"A": A, "B": B, "C": C, "scores": scores}


def _write_matrix(
    directory: Path, catalogue: tuple[_Dataset, ...], matrices: dict[str, np.ndarray]
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _write_sparse(directory / "A_public.csv", matrices["A"], MATRIX_COLUMNS)
    _write_sparse(directory / "B_public.csv", matrices["B"], MATRIX_COLUMNS)
    _write_sparse(directory / "C.csv", matrices["C"], ("row", "column", "coefficient"))
    _write_index(
        directory / "ie_index.csv",
        INDEX_COLUMNS["ie"],
        [
            (
                dataset.name,
                dataset.geography,
                _reference(dataset.flows).name,
                _reference(dataset.flows).unit,
            )
            for dataset in catalogue
        ],
    )
    _write_index(
        directory / "ee_index.csv",
        INDEX_COLUMNS["ee"],
        [
            (name, compartment, subcompartment, "kg")
            for _, name, compartment, subcompartment, _, _ in _ELEMENTARY
        ],
    )
    _write_index(
        directory / "LCIA_index.csv",
        INDEX_COLUMNS["lcia"],
        [(METHOD, CATEGORY, INDICATOR, INDICATOR_UNIT)],
    )


def _write_sparse(path: Path, matrix: np.ndarray, columns: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(columns)
        for row, column in zip(*matrix.nonzero(), strict=True):
            writer.writerow(
                [int(row), int(column), float(matrix[row, column]), *[""] * (len(columns) - 3)]
            )


def _write_index(path: Path, columns: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(columns)
        for position, row in enumerate(rows):
            writer.writerow([*row, position])


def _write_cumulative(
    path: Path, catalogue: tuple[_Dataset, ...], matrices: dict[str, np.ndarray]
) -> None:
    rows: list[list[object]] = [
        ["", "", "", "", "", "Method", METHOD],
        ["", "", "", "", "", "Category", CATEGORY],
        ["", "", "", "", "", "Indicator", INDICATOR],
        [
            "Activity UUID_Product UUID",
            "Activity Name",
            "Geography",
            "Reference Product Name",
            "Reference Product Unit",
            "Reference Product Amount",
            INDICATOR_UNIT,
        ],
    ]
    A = matrices["A"]
    scores = matrices["scores"]
    for position, dataset in enumerate(catalogue):
        reference = _reference(dataset.flows)
        rows.append(
            [
                dataset.native,
                dataset.name,
                dataset.geography,
                reference.name,
                reference.unit,
                A[position, position],
                scores[position, 0],
            ]
        )
    _write_workbook(path, {"LCIA": rows})


def tamper_cumulative(release: Release, native: str, factor: float) -> None:
    """Multiply one dataset's scores in the fixture's cumulative workbook by a factor."""
    sheet = CalamineWorkbook.from_path(str(release.cumulative_lcia)).get_sheet_by_name("LCIA")
    rows = sheet.to_python()
    for row in rows[4:]:
        if str(row[0]) == native:
            for column in range(6, len(row)):
                row[column] = float(row[column]) * factor
    _write_workbook(release.cumulative_lcia, {"LCIA": rows})


def offset_cumulative(release: Release, native: str, amount: float) -> None:
    """Add an amount to one dataset's scores in the fixture's cumulative workbook."""
    sheet = CalamineWorkbook.from_path(str(release.cumulative_lcia)).get_sheet_by_name("LCIA")
    rows = sheet.to_python()
    for row in rows[4:]:
        if str(row[0]) == native:
            for column in range(6, len(row)):
                row[column] = float(row[column]) + amount
    _write_workbook(release.cumulative_lcia, {"LCIA": rows})


def _write_workbook(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    workbook = xlsxwriter.Workbook(str(path))
    for name, rows in sheets.items():
        worksheet = workbook.add_worksheet(name)
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                if isinstance(value, str):
                    worksheet.write_string(row_index, column, value)
                else:
                    worksheet.write_number(row_index, column, value)
    workbook.close()
