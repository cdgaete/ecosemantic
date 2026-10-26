"""Score a USLCI release and its methods from the source zips alone.

    independent_scores.py --inventory ZIP [--bridged ZIP]... --method ZIP...
                           --left-out CSV --out CSV --unlinked-out CSV

The computation shares no code with the core's import, its build or its engine: it reads the
source zips' JSON with the standard library, numpy and scipy, and states openLCA's definitions
here, where it applies them. Where it and the core disagree, `validate` reports both.

- `--bridged` names a repository USLCI's bridges link to, read beside the release: its records
  join the release's where an id is free, the release's record holding a shared one. The processes
  of one repository are converted with the unit groups and flow properties of that repository, its
  authors' factors applying and not the release's.

- The score of one unit of a dataset is per one unit of its flow's reference unit, and each row
  names that unit; an exchange's amount enters in that unit, whether or not its process declared
  another.
- One dataset per product output of a process, coded `<process id>_<product flow id>`; a process
  whose quantitative reference is a waste input is one dataset, treating that waste, coded
  `<process id>_<waste flow id>`. A process that produces nothing and treats nothing is no
  dataset.
- An exchange's amount is in its flow's reference unit: its unit's factor within its flow
  property's group, divided by that flow's factor for the property, multiplied by its factor for
  the reference one. A characterisation factor's value is divided by its unit's factor, which
  gives it per reference unit of the flow it names.
- A dataset's column of the technosphere holds its production on the diagonal, in its flow's
  reference unit: a product output positive, a treated waste input negated. Each technosphere
  input of its process enters the provider's row negated; an avoided product enters it positive; a
  waste output enters its treatment's row positive, which is the sign that runs the treatment when
  the producer runs. A waste input that is not its process's reference is refused, as the build
  refuses it.
- A product input's provider is the process its `defaultProvider` names when that process
  produces the flow; with none named, the process a bridge's description names as
  `defaultProvider.@id` when the zips hold it, a description that is not a JSON object naming
  none; else the one process producing it. A named process that does not produce the flow leaves
  the input unlinked, as the core leaves it. A waste output's provider is the process treating it.
  Anything else is unlinked: it is left out of the matrices and written to `--unlinked-out`, in
  the columns of the source's own list.
- Allocation: a lone product takes every exchange whole. With several, the process's default
  method decides: physical and economic give each product its one factor for every exchange, and
  causal the factor naming the pair of that product and that exchange. A product's own output is
  never allocated, and the other products' outputs are not part of its dataset.
- The intervention holds each elementary exchange's allocated amount, positive whether the
  exchange is taken in or released, in its flow's reference unit.
- `--left-out` is the build's list, applied as the build applies it: a row whose `what` is
  `exchange` drops that exchange by its own id, and a `distribution` row changes no amount, so a
  deterministic score does not move with it; only the exchange rows are read.
- The score of one unit of dataset j under a category is `(A^-T (B^T f))[j]`: one sparse LU of
  the transposed technosphere, and one solve per category.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import zipfile
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

Record = dict[str, object]
ELEMENTARY = "ELEMENTARY_FLOW"
PRODUCT = "PRODUCT_FLOW"
WASTE = "WASTE_FLOW"
PHYSICAL = "PHYSICAL_ALLOCATION"
ECONOMIC = "ECONOMIC_ALLOCATION"
CAUSAL = "CAUSAL_ALLOCATION"
UNLINKED_COLUMNS = (
    "process_id",
    "process_name",
    "flow_id",
    "flow_name",
    "flow_category",
    "provider_id",
)
SCORE_COLUMNS = ("code", "method", "category", "score", "unit")

Unlinked = tuple[str, str, str, str, str, str | None]
Scored = list[tuple[str, str, str, float, str]]


def _id(record: Record) -> str:
    """The id a record declares."""
    return str(record["@id"])


def _name(record: Record) -> str:
    """The name a record carries."""
    return str(record.get("name") or "")


def _listed(record: Record, key: str) -> list[Record]:
    """The records a record holds under a list key, or none when it holds none."""
    return [item for item in record.get(key) or [] if isinstance(item, dict)]


def _reference(record: Record, key: str) -> Record:
    """The reference a record holds under a key, refused when it holds none."""
    found = record.get(key)
    if not isinstance(found, dict):
        raise ValueError(f"{_name(record) or _id(record)} carries no {key}")
    return found


def _number(record: Record, key: str) -> float:
    """The number a record carries under a key."""
    return float(record[key])


def _flag(record: Record, key: str) -> bool:
    """The flag a record carries under a key, false when it carries none."""
    return bool(record.get(key))


def _top(record: Record, key: str) -> str:
    """The first segment of the category a record carries under a key."""
    category = record.get(key)
    return str(category).split("/")[0] if category else ""


def read_zip(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    """Every entity record a package holds, by folder and then by the id the record declares; a
    directory entry or a member under `bin/` is no record."""
    found: dict[str, dict[str, Record]] = collections.defaultdict(dict)
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.endswith(".json") or member.count("/") != 1:
                continue
            record = json.loads(archive.read(member))
            found[member.split("/", 1)[0]][_id(record)] = record
    return dict(found)


def read_left_out(path: Path) -> set[tuple[str, int]]:
    """The process and exchange pairs a left-out list drops, from the rows whose kind is an
    exchange; a process may carry one flow in two exchanges, so the exchange's id names it."""
    with path.open(newline="") as read:
        return {
            (record["process_id"], int(record["exchange_id"]))
            for record in csv.DictReader(read)
            if record["what"] == "exchange"
        }


def _merged(sources: Iterable[dict[str, dict[str, Record]]]) -> dict[str, dict[str, Record]]:
    """Every record of several packages, the earlier package holding a record two of them hold."""
    merged: dict[str, dict[str, Record]] = collections.defaultdict(dict)
    for package in sources:
        for folder, records in package.items():
            for identifier, record in records.items():
                merged[folder].setdefault(identifier, record)
    return dict(merged)


@dataclass(frozen=True)
class _Tables:
    """What the zips' own records state: the flows, every unit's factor by id and by group and
    name, every unit group's reference unit and its name, and the unit group each flow property is
    in."""

    flows: dict[str, Record]
    units: dict[str, float]
    named: dict[tuple[str, str], float]
    groups: dict[str, tuple[str, float]]
    reference_names: dict[str, str]
    properties: dict[str, str]


def _tables(package: dict[str, dict[str, Record]], flows: dict[str, Record]) -> _Tables:
    """The units, unit groups and flow properties a package states for itself, over the flows the
    computation reads."""
    units: dict[str, float] = {}
    named: dict[tuple[str, str], float] = {}
    groups: dict[str, tuple[str, float]] = {}
    reference_names: dict[str, str] = {}
    for identifier, group in package.get("unit_groups", {}).items():
        for unit in _listed(group, "units"):
            units[_id(unit)] = _number(unit, "conversionFactor")
            named[(identifier, _name(unit))] = _number(unit, "conversionFactor")
            if _flag(unit, "isRefUnit"):
                groups[identifier] = (_id(unit), _number(unit, "conversionFactor"))
                reference_names[identifier] = _name(unit)
    return _Tables(
        flows=flows,
        units=units,
        named=named,
        groups=groups,
        reference_names=reference_names,
        properties={
            identifier: _id(_reference(property, "unitGroup"))
            for identifier, property in package.get("flow_properties", {}).items()
        },
    )


def _flow_property(flow: Record) -> tuple[str, float]:
    """A flow's reference flow property, and the factor it declares for it."""
    for declared in _listed(flow, "flowProperties"):
        if _flag(declared, "isRefFlowProperty"):
            return _id(_reference(declared, "flowProperty")), _number(declared, "conversionFactor")
    raise ValueError(f"flow {_name(flow) or _id(flow)} declares no reference flow property")


def _declared(flow: Record, property_id: str) -> float:
    """The factor a flow declares for one of its flow properties."""
    for declared in _listed(flow, "flowProperties"):
        if _id(_reference(declared, "flowProperty")) == property_id:
            return _number(declared, "conversionFactor")
    raise ValueError(f"flow {_name(flow) or _id(flow)} declares no flow property {property_id}")


def _amount(exchange: Record, flow: Record, tables: _Tables) -> float:
    """An exchange's amount in its flow's reference unit, its unit's factor and its flow
    property's factor converting it there."""
    reference_id, reference_factor = _flow_property(flow)
    property_id = _id(_reference(exchange, "flowProperty"))
    given = tables.units[_id(_reference(exchange, "unit"))]
    return (
        _number(exchange, "amount")
        * given
        / tables.groups[tables.properties[property_id]][1]
        / _declared(flow, property_id)
        * reference_factor
    )


def _value(factor: Record, tables: _Tables) -> float:
    """A characterisation factor's value per reference unit of the flow it names, divided by the
    factor of its own unit; a unit its group holds under another id is found by its name."""
    unit = _reference(factor, "unit")
    if _id(unit) in tables.units:
        return _number(factor, "value") / tables.units[_id(unit)]
    group = tables.properties[_id(_reference(factor, "flowProperty"))]
    found = tables.named.get((group, _name(unit)))
    if found is None:
        raise ValueError(f"a factor carries unit {_name(unit)}, which no group of its zip holds")
    return _number(factor, "value") / found


def _flow(exchange: Record, tables: _Tables) -> Record:
    """The flow an exchange names, refused when no zip the computation read holds it."""
    found = tables.flows.get(_id(_reference(exchange, "flow")))
    if found is None:
        raise ValueError(f"exchange {exchange['internalId']} names a flow no zip holds")
    return found


def _unit_of(flow_id: str, tables: _Tables) -> str:
    """The name of the reference unit of a flow's reference property, as its zip writes it."""
    reference_id, _factor = _flow_property(tables.flows[flow_id])
    return tables.reference_names[tables.properties[reference_id]]


def _product_output(exchange: Record, flow: Record) -> bool:
    """Whether an exchange is a product its process produces."""
    return flow.get("flowType") == PRODUCT and not _flag(exchange, "isInput")


def _waste_output(exchange: Record, flow: Record) -> bool:
    """Whether an exchange is a waste its process releases."""
    return flow.get("flowType") == WASTE and not _flag(exchange, "isInput")


def _references(process: Record, tables: _Tables) -> list[Record]:
    """The exchanges a process is one dataset per: its product outputs, or the waste input it
    takes in as its quantitative reference."""
    exchanges = [
        exchange
        for exchange in _listed(process, "exchanges")
        if _id(_reference(exchange, "flow")) in tables.flows
    ]
    products = [
        exchange
        for exchange in exchanges
        if _product_output(exchange, tables.flows[_id(_reference(exchange, "flow"))])
    ]
    if products:
        return products
    return [
        exchange
        for exchange in exchanges
        if _flag(exchange, "isQuantitativeReference")
        and tables.flows[_id(_reference(exchange, "flow"))].get("flowType") == WASTE
    ]


def _providers(
    processes: dict[str, Record], tables: _Tables
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The processes producing each product flow, and those treating each waste flow."""
    producers: dict[str, list[str]] = collections.defaultdict(list)
    treaters: dict[str, list[str]] = collections.defaultdict(list)
    for identifier, process in processes.items():
        for exchange in _listed(process, "exchanges"):
            flow = _flow(exchange, tables)
            if _product_output(exchange, flow):
                producers[_id(flow)].append(identifier)
            if _flag(exchange, "isQuantitativeReference") and flow.get("flowType") == WASTE:
                treaters[_id(flow)].append(identifier)
    return dict(producers), dict(treaters)


def _named(exchange: Record) -> str | None:
    """The id a default provider reference names, or nothing."""
    named = exchange.get("defaultProvider")
    return _id(named) if isinstance(named, dict) else None


def _stated(exchange: Record) -> str | None:
    """The process id an input's description states as `defaultProvider.@id`, or nothing when its
    description is not a JSON object stating one."""
    description = exchange.get("description")
    if not isinstance(description, str):
        return None
    try:
        stated = json.loads(description)
    except json.JSONDecodeError:
        return None
    if not isinstance(stated, dict):
        return None
    named = stated.get("defaultProvider.@id")
    return named if isinstance(named, str) else None


def _requested(exchange: Record, held: Collection[str]) -> str | None:
    """The process an exchange names as its provider: its `defaultProvider`, else, for an input,
    the process its description names when `held` holds it."""
    named = _named(exchange)
    if named is not None or not _flag(exchange, "isInput"):
        return named
    stated = _stated(exchange)
    return stated if stated is not None and stated in held else None


def _provider(
    exchange: Record,
    flow: Record,
    providers: tuple[dict[str, list[str]], dict[str, list[str]]],
    held: Collection[str],
) -> str | None:
    """The process a product input or a waste output is the provider of: the one it names when that
    one offers the flow, else the sole one, else nothing."""
    producers, treaters = providers
    candidates = (treaters if flow.get("flowType") == WASTE else producers).get(_id(flow), [])
    named = _requested(exchange, held)
    if named is not None:
        return named if named in candidates else None
    return candidates[0] if len(candidates) == 1 else None


def _allocated(
    process: Record, references: list[Record], tables: _Tables
) -> dict[tuple[str, int], float]:
    """The share each of a process's references takes of each of its exchanges: whole for a lone
    product, the product's factor under physical and economic allocation, the factor naming the
    pair of product and exchange under causal allocation."""
    exchanges = [int(exchange["internalId"]) for exchange in _listed(process, "exchanges")]
    if len(references) == 1:
        return {(_id(_reference(references[0], "flow")), exchange): 1.0 for exchange in exchanges}
    method = str(process.get("defaultAllocationMethod") or "")
    listed = [
        factor
        for factor in _listed(process, "allocationFactors")
        if factor.get("allocationType") == method
    ]
    if method == CAUSAL:
        return {
            (
                _id(_reference(factor, "product")),
                int(_number(_reference(factor, "exchange"), "internalId")),
            ): _number(factor, "value")
            for factor in listed
        }
    if method in (PHYSICAL, ECONOMIC):
        return {
            (_id(_reference(factor, "product")), exchange): _number(factor, "value")
            for factor in listed
            for exchange in exchanges
        }
    raise ValueError(f"process {_id(process)} produces {len(references)} under {method or 'none'}")


def _share(
    shares: dict[tuple[str, int], float], product_id: str, exchange: Record, process: Record
) -> float:
    """The share one reference takes of one exchange, refused when its process states none."""
    found = shares.get((product_id, int(exchange["internalId"])))
    if found is None:
        raise ValueError(
            f"process {_id(process)} states no factor for product {product_id} and "
            f"exchange {exchange['internalId']}"
        )
    return found


def _columns(
    process: Record, reference: Record, tables: _Tables, left_out: set[tuple[str, int]]
) -> list[Record]:
    """The exchanges a dataset's column carries besides its production: those that are not a
    product's own output, not the reference itself, and not on the left-out list."""
    products = {
        int(exchange["internalId"])
        for exchange in _listed(process, "exchanges")
        if _product_output(exchange, _flow(exchange, tables))
    }
    return [
        exchange
        for exchange in _listed(process, "exchanges")
        if int(exchange["internalId"]) not in products
        and exchange["internalId"] != reference["internalId"]
        and (_id(process), int(exchange["internalId"])) not in left_out
    ]


def _owned(
    packages: Sequence[dict[str, dict[str, Record]]], flows: dict[str, Record]
) -> list[tuple[dict[str, Record], _Tables]]:
    """Every package's processes, each with the units, unit groups and flow properties of the
    package it came from, the earlier package holding a process two of them hold."""
    owned: list[tuple[dict[str, Record], _Tables]] = []
    seen: set[str] = set()
    for package in packages:
        processes = {
            identifier: process
            for identifier, process in package.get("processes", {}).items()
            if identifier not in seen
        }
        if not processes:
            continue
        seen |= set(processes)
        owned.append((processes, _tables(package, flows)))
    return owned


def _matrices(
    owned: Sequence[tuple[dict[str, Record], _Tables]],
    tables: _Tables,
    left_out: set[tuple[str, int]],
) -> tuple[list[str], sp.csc_matrix, list[str], sp.csc_matrix, list[Unlinked]]:
    """The technosphere over one column per dataset, the intervention over one row per elementary
    flow, and the inputs nothing provides."""
    processes = {
        identifier: process
        for owned_processes, _own in owned
        for identifier, process in owned_processes.items()
    }
    providers = _providers(processes, tables)
    held = frozenset(processes)
    columns: dict[str, int] = {}
    plan: list[tuple[str, Record, Record, dict[tuple[str, int], float], _Tables]] = []
    for owned_processes, own in owned:
        for process_id, process in owned_processes.items():
            references = _references(process, own)
            if not references:
                continue
            shares = _allocated(process, references, own)
            for reference in references:
                columns[f"{process_id}_{_id(_reference(reference, 'flow'))}"] = len(plan)
                plan.append((process_id, process, reference, shares, own))
    elementary: dict[str, int] = {}
    technosphere: list[tuple[int, int, float]] = []
    intervention: list[tuple[int, int, float]] = []
    unlinked: list[Unlinked] = []
    for at, (process_id, process, reference, shares, own) in enumerate(plan):
        flow = _flow(reference, own)
        production = _amount(reference, flow, own)
        technosphere.append((at, at, -production if _flag(reference, "isInput") else production))
        for exchange in _columns(process, reference, own, left_out):
            exchanged = _flow(exchange, own)
            allocated = _amount(exchange, exchanged, own) * _share(
                shares, _id(flow), exchange, process
            )
            if exchanged.get("flowType") == ELEMENTARY:
                if _id(exchanged) not in elementary:
                    elementary[_id(exchanged)] = len(elementary)
                intervention.append((elementary[_id(exchanged)], at, allocated))
                continue
            if exchanged.get("flowType") == WASTE and _flag(exchange, "isInput"):
                raise ValueError(
                    f"process {process_id} takes {_name(exchanged)} as a waste input that is not "
                    "its reference"
                )
            provider = _provider(exchange, exchanged, providers, held)
            if provider is None:
                unlinked.append(
                    (
                        process_id,
                        _name(process),
                        _id(exchanged),
                        _name(exchanged),
                        _top(exchanged, "category"),
                        _named(exchange),
                    )
                )
                continue
            sign = (
                1.0
                if _flag(exchange, "isAvoidedProduct") or _waste_output(exchange, exchanged)
                else -1.0
            )
            technosphere.append((columns[f"{provider}_{_id(exchanged)}"], at, allocated * sign))
    return (
        [code for code, _ in sorted(columns.items(), key=lambda item: item[1])],
        _matrix(technosphere, (len(columns), len(columns))),
        [flow for flow, _ in sorted(elementary.items(), key=lambda item: item[1])],
        _matrix(intervention, (len(elementary), len(columns))),
        list({(row[0], row[2], row[5]): row for row in unlinked}.values()),
    )


def _matrix(entries: list[tuple[int, int, float]], shape: tuple[int, int]) -> sp.csc_matrix:
    """One sparse matrix from rows, columns and amounts."""
    rows, columns, amounts = zip(*entries, strict=True) if entries else ((), (), ())
    return sp.csc_matrix((amounts, (rows, columns)), shape=shape)


def _characterised(category: Record, elementary: Sequence[str], tables: _Tables) -> np.ndarray:
    """One category's factors over the elementary flows, summed per flow, per reference unit."""
    vector = np.zeros(len(elementary))
    for factor in _listed(category, "impactFactors"):
        flow_id = _id(_reference(factor, "flow"))
        if flow_id in elementary:
            vector[list(elementary).index(flow_id)] += _value(factor, tables)
    return vector


def _computed(
    inventory: Path,
    methods: Sequence[Path],
    left_out: Path,
    bridged: Sequence[Path] = (),
) -> tuple[Scored, list[Unlinked]]:
    """The score of one unit of every dataset's reference unit under every category of the method
    packages, with the name of that unit, and the inputs the zips leave unlinked, one per process,
    flow and provider, with the columns its list holds."""
    repositories = [read_zip(inventory), *(read_zip(path) for path in bridged)]
    package = _merged([*repositories, *(read_zip(path) for path in methods)])
    flows = package.get("flows", {})
    tables = _tables(package, flows)
    owned = _owned(repositories, flows)
    codes, technosphere, elementary, intervention, unlinked = _matrices(
        owned, tables, read_left_out(left_out)
    )
    solve = splu(technosphere.transpose().tocsc()).solve
    scored: Scored = []
    for method in package.get("lcia_methods", {}).values():
        for reference in _listed(method, "impactCategories"):
            category = package.get("lcia_categories", {}).get(_id(reference))
            if category is None:
                continue
            solved = solve(intervention.transpose() @ _characterised(category, elementary, tables))
            scored += [
                (
                    code,
                    _name(method),
                    _name(category),
                    float(solved[at]),
                    _unit_of(code.split("_", 1)[1], tables),
                )
                for at, code in enumerate(codes)
            ]
    return scored, unlinked


def scores(
    inventory: Path, methods: Sequence[Path], left_out: Path, bridged: Sequence[Path] = ()
) -> tuple[Scored, list[tuple[str, str, str | None]]]:
    """The score of one unit of every dataset's reference unit under every category of the method
    packages, with that unit's name, and the keys of the inputs the zips leave unlinked, the
    release read with the bridged repositories `bridged` names."""
    scored, unlinked = _computed(inventory, methods, left_out, bridged)
    return scored, [(process, flow, provider) for process, _, flow, _, _, provider in unlinked]


def _written(path: Path, columns: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """Write rows as CSV under a header, one line each."""
    with path.open("w", newline="") as written:
        writer = csv.writer(written, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="independent_scores",
        description="Score a USLCI release from its source zips, sharing no code with the core.",
    )
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--bridged", action="append", default=[], type=Path)
    parser.add_argument("--method", required=True, type=Path, nargs="+")
    parser.add_argument("--left-out", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--unlinked-out", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the scores to --out and the unlinked inputs to --unlinked-out."""
    args = _parser().parse_args(argv)
    scored, unlinked = _computed(args.inventory, args.method, args.left_out, args.bridged)
    _written(args.out, SCORE_COLUMNS, scored)
    _written(
        args.unlinked_out,
        UNLINKED_COLUMNS,
        [(row[0], row[1], row[2], row[3], row[4], row[5] or "") for row in unlinked],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
