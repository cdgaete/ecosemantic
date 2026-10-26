"""The structural checks a source's import is held to before its scores are compared."""

from __future__ import annotations

from typing import cast

from ecosemantic.package.background import Dataset, Import


def unnamed(imported: Import) -> list[str]:
    """Every characterisation factor that names no flow of the import, and every technosphere row
    that names no dataset of it."""
    flows = {code for _, code in imported.flows}
    datasets = {code for _, code in imported.datasets}
    found: list[str] = []
    for method in imported.methods:
        for (_, flow), _value in method.factors:
            if flow not in flows:
                found.append(
                    f"{method.key[1]}, {method.key[2]} names flow {flow}, which the import lacks"
                )
    for (_, code), dataset in imported.datasets.items():
        for row in cast(list[Dataset], dataset["exchanges"]):
            target = cast(tuple[str, str], row["input"])[1]
            if row["type"] == "technosphere" and target not in datasets:
                found.append(f"{code} takes {target}, which is no dataset of the import")
    return found
