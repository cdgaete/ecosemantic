"""The fixture databases as openLCA bundles, compiled for the engine and installed for the
bundle store: the processes, flows and methods of tests/fixture_data.py, under which the widget
scores 4.158, and its looped background, whose pellet and heat production feed each other."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.backends.native.install import install
from ecosemantic.engine.background import Background
from ecosemantic.model.entities import Uncertainty
from ecosemantic.model.refs import Database
from ecosemantic.package.background import read_background
from ecosemantic.package.base_writer import (
    BaseDataset,
    BaseExchange,
    BaseFlow,
    BaseMethod,
    BaseRows,
    write_base_bundle,
)
from ecosemantic.package.compile import compile_background
from tests.fixture_data import (
    CODES,
    FIXTURE_DATABASE,
    FIXTURE_DB,
    FLOW_IDS,
    FLOWS,
    LOOP_BIO,
    LOOP_CODES,
    LOOP_DB,
    LOOP_GWP,
    LOOP_PROCESSES,
    METHODS,
    PROCESSES,
    WIDE_NORMALS,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
LOOP_FINGERPRINT = "b644289d954787666e1dce05f1b2c5a09e66265a1c8d541d7804261aa05ac104"
LOOP_DATABASE = Database(
    name=LOOP_DB,
    elementary_flows=LOOP_BIO,
    scheme="olca",
    version="1",
    system_model="unit process",
    fingerprint=LOOP_FINGERPRINT,
)


def _wide(process: str, key: str, amount: float) -> Uncertainty | None:
    """A normal distribution wider than the amount, as the Brightway fixture carries two."""
    scale = WIDE_NORMALS.get((process, key))
    if scale is None:
        return None
    return Uncertainty(type="normal", params={"loc": amount, "scale": scale})


def _flows() -> tuple[BaseFlow, ...]:
    """The fixture's four flows as base bundle flows."""
    return tuple(
        BaseFlow(
            code=FLOW_IDS[key],
            name=name,
            unit=unit,
            categories=categories,
            type="natural resource" if categories[0] == "natural resource" else "emission",
            cas=None,
        )
        for key, (name, categories, unit) in FLOWS.items()
    )


def fixture_rows() -> BaseRows:
    """The fixture's twelve processes, four flows and two methods as base bundle rows."""
    datasets = tuple(
        BaseDataset(
            code=CODES[key],
            native=CODES[key],
            name=name,
            reference_product=product,
            unit=unit,
            location="GLO",
            comment=None,
            url=None,
            exchanges=(
                BaseExchange(kind="production", input=CODES[key], amount=1.0, uncertainty=None),
                *(
                    BaseExchange(
                        kind="technosphere",
                        input=CODES[supplier],
                        amount=amount,
                        uncertainty=_wide(key, supplier, amount),
                    )
                    for supplier, amount in inputs.items()
                ),
                *(
                    BaseExchange(
                        kind="biosphere",
                        input=FLOW_IDS[flow],
                        amount=amount,
                        uncertainty=_wide(key, flow, amount),
                    )
                    for flow, amount in emissions.items()
                ),
            ),
        )
        for key, (name, product, unit, inputs, emissions) in PROCESSES.items()
    )
    flows = _flows()
    methods = tuple(
        BaseMethod(
            key=key,
            unit=unit,
            factors=tuple((FLOW_IDS[flow], value) for flow, value in factors.items()),
        )
        for key, unit, factors in METHODS
    )
    return BaseRows(datasets=datasets, flows=flows, methods=methods)


def fixture_bundle(directory: Path) -> Path:
    """The fixture written as a bundle in a directory."""
    written = write_base_bundle(
        fixture_rows(),
        scheme="olca",
        name=FIXTURE_DB,
        version="1",
        destination=directory / "fixture.zip",
        now=NOW,
    )
    return written.bundle


def fixture_background(directory: Path) -> Background:
    """The fixture's bundle, read and compiled for the engine."""
    imported = read_background(fixture_bundle(directory), FIXTURE_DB, foreground=frozenset())
    return compile_background(imported, FIXTURE_DATABASE)


def looped_rows() -> BaseRows:
    """The looped background's three processes, each input lognormal, as base bundle rows."""
    datasets = tuple(
        BaseDataset(
            code=LOOP_CODES[key],
            native=LOOP_CODES[key],
            name=name,
            reference_product=name.split()[0],
            unit=unit,
            location="GLO",
            comment=None,
            url=None,
            exchanges=(
                BaseExchange(
                    kind="production", input=LOOP_CODES[key], amount=1.0, uncertainty=None
                ),
                *(
                    BaseExchange(
                        kind="technosphere",
                        input=LOOP_CODES[provider],
                        amount=amount,
                        uncertainty=Uncertainty(
                            type="lognormal",
                            params={"loc": math.log(amount), "scale": math.log(gsd)},
                        ),
                    )
                    for provider, (amount, gsd) in inputs.items()
                ),
                BaseExchange(kind="biosphere", input=FLOW_IDS["co2"], amount=co2, uncertainty=None),
            ),
        )
        for key, (name, unit, inputs, co2) in LOOP_PROCESSES.items()
    )
    methods = (BaseMethod(key=LOOP_GWP, unit="kg CO2-Eq", factors=((FLOW_IDS["co2"], 1.0),)),)
    return BaseRows(datasets=datasets, flows=_flows(), methods=methods)


def looped_bundle(directory: Path) -> Path:
    """The looped background written as a bundle in a directory."""
    written = write_base_bundle(
        looped_rows(),
        scheme="olca",
        name=LOOP_DB,
        version="1",
        destination=directory / "looped.zip",
        now=NOW,
    )
    return written.bundle


def looped_background(directory: Path) -> Background:
    """The looped background's bundle, read and compiled for the engine."""
    imported = read_background(looped_bundle(directory), LOOP_DB, foreground=frozenset())
    return compile_background(imported, LOOP_DATABASE)


def install_fixtures(data_dir: Path, sources: Path) -> None:
    """The fixture and the looped background written as bundles in sources and installed under
    the data directory, at version 1 of the unit process system model."""
    for bundle, name in (
        (fixture_bundle(sources), FIXTURE_DB),
        (looped_bundle(sources), LOOP_DB),
    ):
        imported = read_background(bundle, name, foreground=frozenset())
        install(data_dir, imported, bundle, version="1", system_model="unit process")
