"""openLCA's records for a zolca's rows, key by key as `Util`'s writers shape them.

Each function builds the JSON dictionary openLCA writes for one row and never an `olca_schema`
object, whose constructors give a missing `lastChange` the present time and a missing `version`
`01.00.000` — values the database does not hold. `Json.put` writes nothing for a `null` value, so
a `NULL` column writes no key; `JsonExport.handleRefs` answers `null` for an empty list, and a
writer that guards its list skips the key as well, so an empty `sources`, `reviews`, `reviewers`,
`impactFactors`, `impactCategories` or `nwSets` writes nothing. A list a writer builds and adds
unguarded is written as `[]` when empty: a process's `parameters`, `exchanges`, `socialAspects` and
`allocationFactors`, a category's `parameters`, a nw set's `factors`, a data quality system's
`indicators`, an indicator's `scores`, a unit group's `units` and a flow's `flowProperties`.
openLCA writes a stand-in only where it holds a value: a review's `reviewType` becomes `""` and
its `scopes` and `assessment` `[]`. Categories are written as the path strings of
`Categories.PathBuilder`, never as entities; `LIBRARY` is never written, openLCA writing it only
with a flag the standard export does not set.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping

from ecosemantic.databases.zolca.export import geometry, refs, render
from ecosemantic.databases.zolca.export.tables import Tables, foreign
from ecosemantic.errors import Invalid, NotSupported

GLOBAL_SCOPE = "GLOBAL"
IMPACT_SCOPE = "IMPACT"
PROCESS_SCOPE = "PROCESS"
FLOW_PROPERTY_TYPES = {0: "ECONOMIC_QUANTITY", 1: "PHYSICAL_QUANTITY"}
DISTRIBUTIONS = {
    1: ("LOG_NORMAL_DISTRIBUTION", "geomMean", "geomSd"),
    2: ("NORMAL_DISTRIBUTION", "mean", "sd"),
}
AUTHOR, DOCUMENTOR = "F_DATA_GENERATOR", "F_DATA_DOCUMENTOR"


def process(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`ProcessWriter`: a process with its exchanges, documentation, parameters and dq systems."""
    found = _base(tables, "Process", row)
    found["processType"] = row["PROCESS_TYPE"]
    _put(found, "defaultAllocationMethod", row["DEFAULT_ALLOCATION_METHOD"])
    found["isInfrastructureProcess"] = bool(row["INFRASTRUCTURE_PROCESS"])
    _reference(found, tables, "location", "Location", row, "F_LOCATION")
    _put(found, "lastInternalId", row["LAST_INTERNAL_ID"])
    _reference(found, tables, "dqSystem", "DQSystem", row, "F_DQ_SYSTEM")
    _reference(found, tables, "exchangeDqSystem", "DQSystem", row, "F_EXCHANGE_DQ_SYSTEM")
    _reference(found, tables, "socialDqSystem", "DQSystem", row, "F_SOCIAL_DQ_SYSTEM")
    _put(found, "dqEntry", row["DQ_ENTRY"])
    owner = _id(row)
    documentation = foreign(row, "F_PROCESS_DOC")
    if documentation is not None:
        found["processDocumentation"] = _documentation(tables, documentation)
    found["parameters"] = [
        parameter(tables, child)
        for child in tables.children("TBL_PARAMETERS", "F_OWNER", owner)
        if child["SCOPE"] == PROCESS_SCOPE
    ]
    found["exchanges"] = [
        _exchange(tables, row, child)
        for child in tables.children("TBL_EXCHANGES", "F_OWNER", owner)
    ]
    found["socialAspects"] = []
    found["allocationFactors"] = []
    return found


def flow(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`FlowWriter`: a flow with its flow property factors, its type and its location."""
    found = _base(tables, "Flow", row)
    found["flowType"] = row["FLOW_TYPE"]
    _put(found, "cas", row["CAS_NUMBER"])
    _put(found, "formula", row["FORMULA"])
    _put(found, "synonyms", _text_or_none(row["SYNONYMS"]))
    found["isInfrastructureFlow"] = bool(row["INFRASTRUCTURE_FLOW"])
    _reference(found, tables, "location", "Location", row, "F_LOCATION")
    reference = foreign(row, "F_REFERENCE_FLOW_PROPERTY")
    found["flowProperties"] = [
        _flow_property_factor(tables, child, reference=reference)
        for child in tables.children("TBL_FLOW_PROPERTY_FACTORS", "F_FLOW", _id(row))
    ]
    return found


def flow_property(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`FlowPropertyWriter`: a flow property, its type read from the ordinal its column holds."""
    found = _base(tables, "FlowProperty", row)
    stored = _text(row["FLOW_PROPERTY_TYPE"])
    if not stored.isdigit() or int(stored) not in FLOW_PROPERTY_TYPES:
        raise NotSupported(f"flow property {row['NAME']!r} is of type {stored!r}")
    found["flowPropertyType"] = FLOW_PROPERTY_TYPES[int(stored)]
    _reference(found, tables, "unitGroup", "UnitGroup", row, "F_UNIT_GROUP")
    return found


def unit_group(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`UnitGroupWriter`: a unit group and its units, the one it counts in marked as such."""
    found = _base(tables, "UnitGroup", row)
    _reference(found, tables, "defaultFlowProperty", "FlowProperty", row, "F_DEFAULT_FLOW_PROPERTY")
    reference = foreign(row, "F_REFERENCE_UNIT")
    found["units"] = [
        _unit(child, reference=reference)
        for child in tables.children("TBL_UNITS", "F_UNIT_GROUP", _id(row))
    ]
    return found


def location(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`LocationWriter`: a location, its stored geometry decoded to GeoJSON."""
    found = _base(tables, "Location", row)
    _put(found, "code", row["CODE"])
    _put(found, "latitude", row["LATITUDE"])
    _put(found, "longitude", row["LONGITUDE"])
    stored = row["GEODATA"]
    if stored is not None:
        drawn = geometry.geojson(bytes(stored)) if isinstance(stored, bytes) else None
        if drawn is not None:
            found["geometry"] = drawn
    return found


def source(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`SourceWriter`: a source's url, its file and its citation."""
    found = _base(tables, "Source", row)
    _put(found, "url", row["URL"])
    _put(found, "externalFile", row["EXTERNAL_FILE"])
    _put(found, "textReference", row["TEXT_REFERENCE"])
    _put(found, "year", row["SOURCE_YEAR"])
    return found


def actor(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`ActorWriter`: an actor's eight contact columns."""
    found = _base(tables, "Actor", row)
    for key, column in (
        ("address", "ADDRESS"),
        ("city", "CITY"),
        ("country", "COUNTRY"),
        ("email", "EMAIL"),
        ("telefax", "TELEFAX"),
        ("telephone", "TELEPHONE"),
        ("website", "WEBSITE"),
        ("zipCode", "ZIP_CODE"),
    ):
        _put(found, key, row[column])
    return found


def currency(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`CurrencyWriter`: a currency's code, its factor and the currency it counts in."""
    found = _base(tables, "Currency", row)
    _put(found, "code", row["CODE"])
    _put(found, "conversionFactor", row["CONVERSION_FACTOR"])
    _reference(found, tables, "refCurrency", "Currency", row, "F_REFERENCE_CURRENCY")
    return found


def parameter(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`ParameterWriter`: a parameter's scope, its value, its formula and its uncertainty."""
    found = _base(tables, "Parameter", row)
    scope = _text(row["SCOPE"])
    if scope not in (GLOBAL_SCOPE, IMPACT_SCOPE, PROCESS_SCOPE):
        raise NotSupported(f"parameter {row['NAME']!r} is of scope {scope!r}")
    found["parameterScope"] = f"{scope}_SCOPE"
    found["isInputParameter"] = bool(row["IS_INPUT_PARAM"])
    _put(found, "value", row["VALUE"])
    _put(found, "formula", row["FORMULA"])
    uncertainty = _uncertainty(row)
    if uncertainty is not None:
        found["uncertainty"] = uncertainty
    return found


def dq_system(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`DQSystemWriter`: a data quality system with its indicators and their scores."""
    found = _base(tables, "DQSystem", row)
    found["hasUncertainties"] = bool(row["HAS_UNCERTAINTIES"])
    _reference(found, tables, "source", "Source", row, "F_SOURCE")
    found["indicators"] = [
        _indicator(tables, child)
        for child in tables.children("TBL_DQ_INDICATORS", "F_DQ_SYSTEM", _id(row))
    ]
    return found


def impact_method(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`ImpactMethodWriter`: a method with the categories it links and its normalisation sets."""
    found = _base(tables, "ImpactMethod", row)
    _put(found, "code", row["CODE"])
    _reference(found, tables, "source", "Source", row, "F_SOURCE")
    categories = [
        refs.ref(tables, "ImpactCategory", _key(link, "F_IMPACT_CATEGORY"))
        for link in tables.children("TBL_IMPACT_LINKS", "F_IMPACT_METHOD", _id(row))
    ]
    if categories:
        found["impactCategories"] = categories
    sets = [
        _nw_set(tables, child)
        for child in tables.children("TBL_NW_SETS", "F_IMPACT_METHOD", _id(row))
    ]
    if sets:
        found["nwSets"] = sets
    return found


def impact_category(tables: Tables, row: dict[str, object]) -> dict[str, object]:
    """`ImpactCategoryWriter`: a category with its parameters and its impact factors."""
    found = _base(tables, "ImpactCategory", row)
    _put(found, "code", row["CODE"])
    _put(found, "refUnit", row["REFERENCE_UNIT"])
    _put(found, "direction", row["DIRECTION"])
    _reference(found, tables, "source", "Source", row, "F_SOURCE")
    owner = _id(row)
    found["parameters"] = [
        parameter(tables, child)
        for child in tables.children("TBL_PARAMETERS", "F_OWNER", owner)
        if child["SCOPE"] == IMPACT_SCOPE
    ]
    factors = [
        _impact_factor(tables, child)
        for child in tables.children("TBL_IMPACT_FACTORS", "F_IMPACT_CATEGORY", owner)
    ]
    if factors:
        found["impactFactors"] = factors
    return found


def _base(tables: Tables, model: str, row: Mapping[str, object]) -> dict[str, object]:
    """`Util.mapBasicAttributes`: the type, the id, the name and what every root entity carries."""
    found: dict[str, object] = {"@type": model, "@id": row["REF_ID"]}
    _put(found, "name", row["NAME"])
    _put(found, "description", row["DESCRIPTION"])
    category = render.category_path(tables, foreign(row, "F_CATEGORY"))
    if category is not None:
        found["category"] = category
    found["version"] = render.version(_int(row["VERSION"]))
    instant = render.instant(_int(row["LAST_CHANGE"]))
    if instant is not None:
        found["lastChange"] = instant
    tags = render.tags(_text_or_none(row["TAGS"]))
    if tags:
        found["tags"] = tags
    return found


def _exchange(
    tables: Tables, owner: Mapping[str, object], row: Mapping[str, object]
) -> dict[str, object]:
    """`ProcessWriter.mapExchange`: an exchange, its flow, unit, provider and uncertainty."""
    found: dict[str, object] = {
        "@type": "Exchange",
        "internalId": row["INTERNAL_ID"],
        "isInput": bool(row["IS_INPUT"]),
        "isAvoidedProduct": bool(row["AVOIDED_PRODUCT"]),
    }
    _put(found, "amount", row["RESULTING_AMOUNT_VALUE"])
    _put(found, "amountFormula", row["RESULTING_AMOUNT_FORMULA"])
    _put(found, "dqEntry", row["DQ_ENTRY"])
    _put(found, "description", row["DESCRIPTION"])
    _put(found, "costValue", row["COST_VALUE"])
    _put(found, "costFormula", row["COST_FORMULA"])
    _put(found, "baseUncertainty", row["BASE_UNCERTAINTY"])
    factor = tables.row("TBL_FLOW_PROPERTY_FACTORS", _key(row, "F_FLOW_PROPERTY_FACTOR"))
    found["flowProperty"] = refs.ref(tables, "FlowProperty", _key(factor, "F_FLOW_PROPERTY"))
    found["flow"] = refs.ref(tables, "Flow", _key(row, "F_FLOW"))
    found["unit"] = refs.ref(tables, "Unit", _key(row, "F_UNIT"))
    _reference(found, tables, "defaultProvider", "Process", row, "F_DEFAULT_PROVIDER")
    _reference(found, tables, "currency", "Currency", row, "F_CURRENCY")
    _reference(found, tables, "location", "Location", row, "F_LOCATION")
    if _id(row) == owner["F_QUANTITATIVE_REFERENCE"]:
        found["isQuantitativeReference"] = True
    uncertainty = _uncertainty(row)
    if uncertainty is not None:
        found["uncertainty"] = uncertainty
    return found


def _documentation(tables: Tables, documentation: int) -> dict[str, object]:
    """`ProcessWriter.mapDoc`: a process's documentation, its sources and its reviews."""
    row = tables.row("TBL_PROCESS_DOCS", documentation)
    found: dict[str, object] = {}
    _put(found, "validFrom", _day(row["VALID_FROM"]))
    _put(found, "validUntil", _day(row["VALID_UNTIL"]))
    for key, column in (
        ("timeDescription", "TIME"),
        ("geographyDescription", "GEOGRAPHY"),
        ("technologyDescription", "TECHNOLOGY"),
        ("inventoryMethodDescription", "INVENTORY_METHOD"),
        ("modelingConstantsDescription", "MODELING_CONSTANTS"),
        ("completenessDescription", "DATA_COMPLETENESS"),
        ("dataSelectionDescription", "DATA_SELECTION"),
        ("dataTreatmentDescription", "DATA_TREATMENT"),
        ("samplingDescription", "SAMPLING_PROCEDURE"),
        ("dataCollectionDescription", "DATA_COLLECTION_PERIOD"),
        ("useAdvice", "USE_ADVICE"),
        ("intendedApplication", "INTENDED_APPLICATION"),
        ("projectDescription", "PROJECT"),
        ("restrictionsDescription", "ACCESS_RESTRICTIONS"),
    ):
        _put(found, key, _written(row[column]))
    _put(found, "creationDate", _local(row["CREATION_DATE"]))
    found["isCopyrightProtected"] = bool(row["COPYRIGHT"])
    _reference(found, tables, "dataGenerator", "Actor", row, AUTHOR)
    _reference(found, tables, "dataDocumentor", "Actor", row, DOCUMENTOR)
    _reference(found, tables, "dataSetOwner", "Actor", row, "F_DATA_OWNER")
    _reference(found, tables, "publication", "Source", row, "F_PUBLICATION")
    sources = [
        refs.ref(tables, "Source", _key(link, "F_SOURCE"))
        for link in tables.children("TBL_SOURCE_LINKS", "F_OWNER", documentation)
    ]
    if sources:
        found["sources"] = sources
    reviews = [
        _review(tables, child) for child in tables.children("TBL_REVIEWS", "F_OWNER", documentation)
    ]
    if reviews:
        found["reviews"] = reviews
    if row["FLOW_COMPLETENESS"] is not None:
        raise NotSupported("a process document's flowCompleteness is not read")
    return found


def _review(tables: Tables, row: Mapping[str, object]) -> dict[str, object]:
    """`ProcessWriter.mapReview`: a review, its `reviewType` as text and its reviewers."""
    found: dict[str, object] = {
        "reviewType": _text_or_none(row["REVIEW_TYPE"]) or "",
        "scopes": _aspects(row["SCOPES"]),
        "assessment": _aspects(row["ASSESSMENT"]),
    }
    _put(found, "details", _written(row["DETAILS"]))
    _reference(found, tables, "report", "Source", row, "F_REPORT")
    reviewers = [
        refs.ref(tables, "Actor", _key(link, "F_ACTOR"))
        for link in tables.children("TBL_ACTOR_LINKS", "F_OWNER", _id(row))
    ]
    if reviewers:
        found["reviewers"] = reviewers
    return found


def _unit(row: Mapping[str, object], *, reference: int | None) -> dict[str, object]:
    """`UnitWriter`: a unit, which carries no version, no tags and no category."""
    found: dict[str, object] = {"@type": "Unit", "@id": row["REF_ID"]}
    _put(found, "name", row["NAME"])
    _put(found, "description", row["DESCRIPTION"])
    _put(found, "conversionFactor", row["CONVERSION_FACTOR"])
    _put(found, "synonyms", _synonyms(row["SYNONYMS"]))
    if _id(row) == reference:
        found["isRefUnit"] = True
    return found


def _flow_property_factor(
    tables: Tables, row: Mapping[str, object], *, reference: int | None
) -> dict[str, object]:
    """`FlowWriter.mapFactor`: a flow's property factor, its reference property marked as such."""
    property_id = _key(row, "F_FLOW_PROPERTY")
    found: dict[str, object] = {"@type": "FlowPropertyFactor"}
    if property_id == reference:
        found["isRefFlowProperty"] = True
    found["flowProperty"] = refs.ref(tables, "FlowProperty", property_id)
    _put(found, "conversionFactor", row["CONVERSION_FACTOR"])
    return found


def _indicator(tables: Tables, row: Mapping[str, object]) -> dict[str, object]:
    """`DQSystemWriter.mapIndicator`: an indicator, which carries no id, with its scores."""
    found: dict[str, object] = {"position": row["POSITION"]}
    _put(found, "name", row["NAME"])
    found["scores"] = [
        _score(child) for child in tables.children("TBL_DQ_SCORES", "F_DQ_INDICATOR", _id(row))
    ]
    return found


def _score(row: Mapping[str, object]) -> dict[str, object]:
    """`DQSystemWriter.mapScore`: one score's position, label, description and uncertainty."""
    found: dict[str, object] = {}
    _put(found, "position", row["POSITION"])
    _put(found, "label", row["LABEL"])
    _put(found, "description", _written(row["DESCRIPTION"]))
    _put(found, "uncertainty", row["UNCERTAINTY"])
    return found


def _nw_set(tables: Tables, row: Mapping[str, object]) -> dict[str, object]:
    """`ImpactMethodWriter.mapNwSet`: a normalisation and weighting set with its factors."""
    found: dict[str, object] = {"@type": "NwSet", "@id": row["REF_ID"]}
    _put(found, "name", row["NAME"])
    _put(found, "description", row["DESCRIPTION"])
    _put(found, "weightedScoreUnit", row["WEIGHTED_SCORE_UNIT"])
    found["factors"] = [
        _nw_factor(tables, child)
        for child in tables.children("TBL_NW_FACTORS", "F_NW_SET", _id(row))
    ]
    return found


def _nw_factor(tables: Tables, row: Mapping[str, object]) -> dict[str, object]:
    """`ImpactMethodWriter.mapNwSet`: one factor's category and the two values it states."""
    found: dict[str, object] = {
        "impactCategory": refs.ref(tables, "ImpactCategory", _key(row, "F_IMPACT_CATEGORY"))
    }
    _put(found, "normalisationFactor", row["NORMALISATION_FACTOR"])
    _put(found, "weightingFactor", row["WEIGHTING_FACTOR"])
    return found


def _impact_factor(tables: Tables, row: Mapping[str, object]) -> dict[str, object]:
    """`ImpactCategoryWriter.mapFactor`: a factor's value, formula, flow, unit and location."""
    found: dict[str, object] = {}
    _put(found, "value", row["VALUE"])
    _put(found, "formula", row["FORMULA"])
    found["flow"] = refs.ref(tables, "Flow", _key(row, "F_FLOW"))
    found["unit"] = refs.ref(tables, "Unit", _key(row, "F_UNIT"))
    factor = tables.row("TBL_FLOW_PROPERTY_FACTORS", _key(row, "F_FLOW_PROPERTY_FACTOR"))
    found["flowProperty"] = refs.ref(tables, "FlowProperty", _key(factor, "F_FLOW_PROPERTY"))
    _reference(found, tables, "location", "Location", row, "F_LOCATION")
    uncertainty = _uncertainty(row)
    if uncertainty is not None:
        found["uncertainty"] = uncertainty
    return found


def _uncertainty(row: Mapping[str, object]) -> dict[str, object] | None:
    """`Uncertainties.of`: the distribution a row states, with the two parameters it names."""
    kind = row["DISTRIBUTION_TYPE"]
    if not kind:
        return None
    if not isinstance(kind, int) or kind not in DISTRIBUTIONS:
        raise NotSupported(f"distribution type {kind!r} is not one the reader takes")
    label, first, second = DISTRIBUTIONS[kind]
    found: dict[str, object] = {"@type": "Uncertainty", "distributionType": label}
    _put(found, first, row["PARAMETER1_VALUE"])
    _put(found, second, row["PARAMETER2_VALUE"])
    return found


def _aspects(stored: object) -> list[object]:
    """`ProcessWriter.mapAspects`: an aspect map, which no database read here stores."""
    if stored is None:
        return []
    raise NotSupported("an aspect map is not one the reader takes")


def _synonyms(value: object) -> list[str] | None:
    """`UnitWriter.map`: a unit's synonyms, which a blank column does not write."""
    text = _text_or_none(value)
    if text is None or not text.strip():
        return None
    return render.synonyms(text)


def _written(value: object) -> object:
    """A column whose text openLCA writes as it stands, `""` included."""
    return None if value is None else _text(value)


def _day(value: object) -> str | None:
    """A stored `DATE` as `yyyy-MM-dd`."""
    if value is None:
        return None
    if not isinstance(value, datetime.date):
        raise Invalid(f"a validity boundary is {value!r}, no date")
    return value.isoformat()


def _local(value: object) -> str | None:
    """A stored `TIMESTAMP` as the local date-time openLCA's writer is given, with no zone."""
    if value is None:
        return None
    if not isinstance(value, datetime.datetime):
        raise Invalid(f"a creation date is {value!r}, no timestamp")
    return value.isoformat(sep="T")


def _put(found: dict[str, object], key: str, value: object) -> None:
    """Write one key, leaving it out where the column is `NULL`."""
    if value is not None:
        found[key] = value


def _reference(
    found: dict[str, object],
    tables: Tables,
    key: str,
    model: str,
    row: Mapping[str, object],
    column: str,
) -> None:
    """Write one reference, leaving the key out where the column names no row."""
    named = foreign(row, column)
    if named is not None:
        found[key] = refs.ref(tables, model, named)


def _id(row: Mapping[str, object]) -> int:
    """A row's own `ID`."""
    found = row["ID"]
    if not isinstance(found, int):
        raise Invalid(f"a row's ID is {found!r}")
    return found


def _key(row: Mapping[str, object], column: str) -> int:
    """A foreign key a record cannot be written without."""
    found = foreign(row, column)
    if found is None:
        raise Invalid(f"{column} names no row")
    return found


def _int(value: object) -> int:
    """A column that always holds a number, `0` where it holds nothing."""
    return 0 if value is None else int(str(value))


def _text(value: object) -> str:
    """A column that always holds text."""
    if not isinstance(value, str):
        raise Invalid(f"{value!r} is no text")
    return value


def _text_or_none(value: object) -> str | None:
    """A column that holds text or nothing."""
    return None if value is None else _text(value)
