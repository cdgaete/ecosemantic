"""Import a database bundle into an empty openLCA database and calculate its product systems.

Runs olca-core's `JsonImport` from the openLCA 2.7 install under the home directory, on that
install's own JRE through JPype, against `Derby.createInMemory()`:
    uv run --with jpype1 python scripts/olca_import_check.py --bundle work.zip
Prints one JSON line with the number of exchanges left without a flow, then one line per
product system, parameter set and impact category with the value openLCA calculates; a system
without parameter sets is calculated once under the case name `base`. Not part of CI: it needs
the openLCA install.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import jpype

OPENLCA = Path.home() / "openLCA"
JVM = OPENLCA / "jre/lib/server/libjvm.so"
LIBS = OPENLCA / "plugins/olca-app_2.7.0/libs"


def _classes() -> dict[str, object]:
    jpype.startJVM(str(JVM), classpath=[str(p) for p in LIBS.glob("*.jar")], convertStrings=True)
    names = {
        "Derby": "org.openlca.core.database.Derby",
        "ZipStore": "org.openlca.jsonld.ZipStore",
        "JsonImport": "org.openlca.jsonld.input.JsonImport",
        "ProcessDao": "org.openlca.core.database.ProcessDao",
        "ProductSystemDao": "org.openlca.core.database.ProductSystemDao",
        "ImpactMethodDao": "org.openlca.core.database.ImpactMethodDao",
        "SystemCalculator": "org.openlca.core.math.SystemCalculator",
        "JavaSolver": "org.openlca.core.matrix.solvers.JavaSolver",
        "CalculationSetup": "org.openlca.core.model.CalculationSetup",
        "File": "java.io.File",
    }
    return {key: jpype.JClass(name) for key, name in names.items()}


def check(bundle: Path) -> list[dict[str, object]]:
    """The empty-exchange count and every calculated value, as JSON-ready rows."""
    j = _classes()
    db = j["Derby"].createInMemory()
    with j["ZipStore"].open(j["File"](str(bundle))) as store:
        j["JsonImport"](store, db).run()
    empty = sum(1 for p in j["ProcessDao"](db).getAll() for e in p.exchanges if e.flow is None)
    rows: list[dict[str, object]] = [{"empty_exchanges": empty}]
    calculator = j["SystemCalculator"](db).withSolver(j["JavaSolver"]())
    for system in j["ProductSystemDao"](db).getAll():
        sets = [(s.name, s.parameters) for s in system.parameterSets] or [("base", None)]
        for method in j["ImpactMethodDao"](db).getAll():
            for case, parameters in sets:
                setup = j["CalculationSetup"].of(system).withImpactMethod(method)
                if parameters is not None:
                    setup = setup.withParameters(parameters)
                result = calculator.calculate(setup)
                for value in result.getTotalImpacts():
                    rows.append(
                        {
                            "system": str(system.refId),
                            "case": str(case),
                            "method": str(method.name),
                            "category": str(value.impact().name),
                            "value": float(value.value()),
                        }
                    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    for row in check(args.bundle):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
